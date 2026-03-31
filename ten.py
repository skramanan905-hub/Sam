import requests, time, json, os, re
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ================= MASTER DATA =================
API_URL = "https://api.pixai.art/graphql"
H_GEN   = "61b5dafa7ade64f847051cdca7024b359bae652421834b8f78423d7640f17d96"
H_POLL  = "a32947c6b546befddacd08a3af63cc4ee2277af27fd43342a01fc0414fca3e8a"
H_LORA  = "4e1614f7373d676cb8ec17975796188369ce321a6e78336558ec50f0c2317840"
H_SEARCH_LORA = "4d76952c681f7d0787077ddeec310f6475ab059e50546248120617abfb4031e9"
H_SEARCH_MODEL = "1658f8e716184e95d3177d20fad189d8f7b250fb30e8401496ed0aaf34e4ad83"
H_LIST  = "cc067203ddd0846c19d9e247d837c32da498247ec252fe30828434f2f136f53d"
H_CRE   = "9356b42a4ff6e987347a1f1ee3de7aba4bd103b1cdbfbbc4c5c5fcf52767ad66"
H_UPLOAD = "dd71971acde11807d01862ff1a94657479f7e833af75eac850aa2de0a14fa1fa"
H_BOOKMARK = "98ec6dc4d4e288b92fed763241f14f65d7dace28de068e4180a90c1248cacdf4"

def get_h(t): 
    return {"Authorization": f"Bearer {t.strip()}", "Content-Type": "application/json", "x-browser-id": "08df9bc9358ad97ebfe0ac86284587e5", "User-Agent": "Mozilla/5.0 (Linux; Android 15; I2301) AppleWebKit/537.36"}

# --- UPDATE 2: BOOKMARK (ADD/REMOVE) ---
@app.route('/api/bookmark', methods=['POST'])
def bookmark():
    d = request.json
    p = {"operationName": "markGenerationModel", "variables": {"modelId": d['id'], "target": d['status'], "type": "BOOKMARK"}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_BOOKMARK}}}
    return jsonify(requests.post(API_URL, json=p, headers=get_h(d['token'])).json())

# --- UPDATE 1: FULL HISTORY (MATCHES YOUR SCREENSHOT) ---
@app.route('/api/tasks', methods=['POST'])
def tasks():
    d = request.json
    fields = ["extra", "prompts", "negativePrompts", "samplingSteps", "samplingMethod", "cfgScale", "width", "height", "loraParameters", "modelId"]
    p = {"operationName": "listMyTasks", "variables": json.dumps({"last": 30, "before": d.get("cursor"), "parameterFields": fields}), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_LIST}})}
    try:
        r = requests.get(API_URL, params=p, headers=get_h(d['token'])).json()
        edges = r['data']['me']['tasks']['edges']
        task_data = []
        for e in edges:
            n = e['node']
            if n['status'] == "completed":
                params = n['parameters']
                task_data.append({
                    "id": n['id'], "url": n['media']['urls'][0]['url'],
                    "prompt": params.get('prompts'), "neg": params.get('negativePrompts'),
                    "steps": params.get('samplingSteps'), "method": params.get('samplingMethod'),
                    "cfg": params.get('cfgScale'), "size": f"{params.get('width')}x{params.get('height')}",
                    "model": n.get('modelId', "Haruka v2"),
                    "loras": params.get('loraParameters', [])
                })
        return jsonify({"tasks": task_data, "cursor": r['data']['me']['tasks']['pageInfo']['startCursor']})
    except: return jsonify({"status": "error"})

# --- UPDATE 3: SEARCH MODELS & LORAS ---
@app.route('/api/search', methods=['POST'])
def search():
    d = request.json
    is_m = d.get('is_model', False)
    h = H_SEARCH_MODEL if is_m else H_SEARCH_LORA
    t_str = "ANY_MODEL" if is_m else "ANY_LORA"
    vars = {"keyword": d['keyword'], "feed": "meilisearch", "types": [t_str], "first": 20, "after": d.get('cursor')}
    p = {"operationName": "listGenerationModels", "variables": json.dumps(vars), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": h}})}
    r = requests.get(API_URL, params=p, headers=get_h(d['token'])).json()
    res = [{"id": n['node']['id'], "name": n['node']['title'], "thumb": next((u['url'] for u in n['node']['media']['urls'] if u['variant'] == "STILL_THUMBNAIL"), "https://pixai.art/favicon.ico")} for n in r['data']['generationModels']['edges']]
    return jsonify({"results": res, "cursor": r['data']['generationModels']['pageInfo']['endCursor']})

# --- GENERATE (BYPASS + PRIORITY) ---
@app.route('/api/generate', methods=['POST'])
def generate():
    d = request.json
    l_w, l_p, trigs = {}, [], ""
    for l in d['lora_configs']:
        l_w[l['v_id']] = float(l['weight'])
        trigs += f", {l['triggers']}"
        l_p.append({"versionId": l['v_id'], "weight": float(l['weight']), "triggerWords": l['triggers'], "positionInfo": {"startIndex": 0, "endIndex": 0}})

    payload = {"operationName": "createGenerationTask", "variables": {"parameters": {"prompts": d['prompt'] + trigs, "negativePrompts": d['neg'], "modelId": d.get('model_id'), "width": int(d['w']), "height": int(d['h']), "batchSize": int(d['batch']), "lora": l_w, "loraParameters": l_p, "samplingSteps": int(d['steps']), "samplingMethod": "Euler a", "cfgScale": float(d['cfg']), "priority": 1000 if d.get('high_priority') else 0, "promptHelper": {"withStage": True, "userWantToEnable": True, "enable": True}}, "extra": {"naturalPrompts": [d['prompt']]}}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_GEN}}}
    
    r = requests.post(API_URL, json=payload, headers=get_h(d['token'])).json()
    tid = r['data']['createGenerationTask']['id']
    while True:
        time.sleep(10)
        poll = {"operationName":"getTaskById","variables":json.dumps({"id":tid}),"extensions":json.dumps({"persistedQuery":{"version":1,"sha256Hash":H_POLL}})}
        sr = requests.get(API_URL, params=poll, headers=get_h(d['token'])).json()
        task = sr['data']['task']
        if task['status'] == "completed":
            return jsonify({"status": "success", "images": [u['url'] for u in task['media']['urls'] if u['variant'] == "PUBLIC"]})
        if task['status'] == "failed": return jsonify({"status": "failed"})

@app.route('/api/lora_meta', methods=['POST'])
def lora_meta():
    d = request.json
    p = {"operationName": "getGenerationModel", "variables": json.dumps({"id": d['id']}), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_LORA}})}
    r = requests.get(API_URL, params=p, headers=get_h(d['token'])).json()
    v = r['data']['generationModel']['latestAvailableVersion']
    return jsonify({"v_id": v['id'], "trigger": v['extra'].get('triggerWords', ""), "name": r['data']['generationModel']['title']})

@app.route('/api/credits', methods=['POST'])
def credits():
    d = request.json
    p = {"operationName":"getMyQuota","variables":"{}","extensions":json.dumps({"persistedQuery":{"version":1,"sha256Hash":H_CRE}})}
    r = requests.get(API_URL, params=p, headers=get_h(d['token'])).json()
    return jsonify({"credits": r['data']['me']['quotaAmount']})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
