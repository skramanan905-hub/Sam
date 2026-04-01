import requests, time, json, re, os
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ================= MASTER CONFIGURATION (FROM YOUR SEVEN.PY) =================
API_URL = "https://api.pixai.art/graphql"
H_GEN    = "61b5dafa7ade64f847051cdca7024b359bae652421834b8f78423d7640f17d96"
H_POLL   = "a32947c6b546befddacd08a3af63cc4ee2277af27fd43342a01fc0414fca3e8a"
H_LORA   = "4e1614f7373d676cb8ec17975796188369ce321a6e78336558ec50f0c2317840"
H_ROLL   = "f0778d88963cc4e40749a8ecd9d510808b4a14cd63fac498e7763e6d5d780e5e"
H_REW    = "923002464a8e816706394061c18316cd2d14f5f025dbd1d08020e44cd8a23546"
H_CRE    = "9356b42a4ff6e987347a1f1ee3de7aba4bd103b1cdbfbbc4c5c5fcf52767ad66"
H_LIST   = "cc067203ddd0846c19d9e247d837c32da498247ec252fe30828434f2f136f53d"
H_UPLOAD = "dd71971acde11807d01862ff1a94657479f7e833af75eac850aa2de0a14fa1fa"
H_SEARCH = "4d76952c681f7d0787077ddeec310f6475ab059e50546248120617abfb4031e9"
H_MARK   = "98ec6dc4d4e288b92fed763241f14f65d7dace28de068e4180a90c1248cacdf4"

def get_h(t): 
    return {
        "Authorization": f"Bearer {t.strip()}", 
        "Content-Type": "application/json", 
        "x-browser-id": "08df9bc9358ad97ebfe0ac86284587e5", 
        "User-Agent": "Mozilla/5.0 (Linux; Android 15; I2301 Build/AP3A.240905.015.A2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Mobile Safari/537.36"
    }

def clean_txt(text):
    return re.sub(r'[_*`\[\]()~>#+\-={}|.!]', '', str(text)) if text else ""

# --- UPDATED HISTORY (NEWEST FIRST + PRO DATA) ---
@app.route('/api/tasks', methods=['POST'])
def tasks():
    d = request.json
    p = {"operationName": "listMyTasks", "variables": json.dumps({"last": 30, "before": d.get("cursor"), "parameterFields": ["extra", "prompts"]}), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_LIST}})}
    try:
        r = requests.get(API_URL, params=p, headers=get_h(d.get("token"))).json()
        edges = r['data']['me']['tasks']['edges']
        task_data = []
        fmt = "%Y-%m-%dT%H:%M:%S.%fZ"
        for edge in reversed(edges):
            n = edge['node']
            if n['status'] == "completed":
                try:
                    c, s, e = datetime.strptime(n['createdAt'], fmt), datetime.strptime(n['startedAt'], fmt), datetime.strptime(n['endedAt'], fmt)
                    wait, gen = int((s - c).total_seconds()), int((e - s).total_seconds())
                except: wait, gen = 0, 0
                task_data.append({
                    "id": n['id'], "url": n['media']['urls'][0]['url'], "p": clean_txt(n['parameters']['prompts']),
                    "neg": n['parameters'].get('negativePrompts', ""), "size": f"{n['parameters']['width']}x{n['parameters']['height']}",
                    "wait": wait, "gen": gen, "sub": n['createdAt'], "model": n['parameters'].get('modelId', "Haruka v2")
                })
        return jsonify({"status": "success", "tasks": task_data, "cursor": r['data']['me']['tasks']['pageInfo']['startCursor'] if r['data']['me']['tasks']['pageInfo']['hasPreviousPage'] else None})
    except: return jsonify({"status": "error"})

# --- LORA META FOR THE "X" CANCEL LOGIC ---
@app.route('/api/lora_meta', methods=['POST'])
def lora_meta():
    d = request.json
    p = {"operationName": "getGenerationModel", "variables": json.dumps({"id": d.get("id")}), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_LORA}})}
    try:
        res = requests.get(API_URL, params=p, headers=get_h(d.get("token"))).json()
        v = res['data']['generationModel']['latestAvailableVersion']
        thumb = next((u['url'] for u in res['data']['generationModel']['media']['urls'] if u['variant'] == "STILL_THUMBNAIL"), "")
        return jsonify({"v_id": v['id'], "trigger": v['extra'].get('triggerWords', ""), "name": res['data']['generationModel']['title'], "thumb": thumb})
    except: return jsonify({"error": "not found"})

# --- GENERATION (EXACT SEVEN.PY LOGIC) ---
@app.route('/api/generate', methods=['POST'])
def generate():
    d = request.json
    token, prompt = d.get("token"), d.get("prompt")
    lora_configs = d.get("lora_configs", [])
    batch, mediaId, strength = int(d.get("batch", 1)), d.get("mediaId"), float(d.get("strength", 0.55))
    w, h, steps, cfg, neg = int(d.get("w", 832)), int(d.get("h", 1248)), int(d.get("steps", 28)), float(d.get("cfg", 5.0)), d.get("neg", "")

    l_w, l_p, all_t = {}, [], ""
    for c in lora_configs:
        l_w[c['v_id']] = float(c['weight'])
        all_t += f"{c['triggers']}, "
        l_p.append({"versionId": c['v_id'], "weight": float(c['weight']), "triggerWords": c['triggers'], "positionInfo": {"startIndex": 0, "endIndex": 0}})

    payload = {
        "operationName": "createGenerationTask",
        "variables": {
            "parameters": {
                "prompts": prompt + ", " + all_t, "negativePrompts": neg,
                "modelId": "1861558740588989558", "width": w, "height": h, "batchSize": batch,
                "lora": l_w, "loraParameters": l_p, "mediaId": mediaId, "strength": strength,
                "samplingSteps": steps, "samplingMethod": "Euler a", "cfgScale": cfg,
                "promptHelper": {"withStage": True, "userWantToEnable": True, "enable": True}
            },
            "extra": {"naturalPrompts": [prompt]}
        },
        "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_GEN}}
    }
    try:
        res = requests.post(API_URL, json=payload, headers=get_h(token)).json()
        tid = res['data']['createGenerationTask']['id']
        for _ in range(35):
            time.sleep(15)
            sr = requests.get(API_URL, params={"operationName":"getTaskById","variables":json.dumps({"id":tid}),"extensions":json.dumps({"persistedQuery":{"version":1,"sha256Hash":H_POLL}})}, headers=get_h(token)).json()
            if sr['data']['task']['status'] == "completed":
                return jsonify({"status": "success", "images": [i['url'] for i in sr['data']['task']['media']['urls'] if i['variant'] == "PUBLIC"]})
        return jsonify({"status": "error"})
    except: return jsonify({"status": "error"})

# --- SEARCH, BOOKMARK, UPLOAD, DELETE, CREDITS ---
@app.route('/api/search', methods=['POST'])
def search():
    d = request.json
    v = {"keyword": d.get("keyword"), "feed": "meilisearch", "types": [d.get("type", "ANY_LORA")], "first": 30, "after": d.get("cursor")}
    r = requests.get(API_URL, params={"operationName":"listGenerationModels","variables":json.dumps(v),"extensions":json.dumps({"persistedQuery":{"version":1,"sha256Hash":H_SEARCH}})}, headers=get_h(d.get("token"))).json()
    items = [{"name": n['node']['title'], "id": n['node']['id'], "thumb": next((u['url'] for u in n['node']['media']['urls'] if u['variant'] == "STILL_THUMBNAIL"), "")} for n in r['data']['generationModels']['edges']]
    return jsonify({"results": items, "cursor": r['data']['generationModels']['pageInfo']['endCursor'] if r['data']['generationModels']['pageInfo']['hasNextPage'] else None})

@app.route('/api/bookmark', methods=['POST'])
def bookmark():
    d = request.json
    p = {"operationName":"markGenerationModel","variables":{"id":d.get("id"),"target":d.get("target"),"type":"BOOKMARK"},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_MARK}}}
    requests.post(API_URL, json=p, headers=get_h(d.get("token")))
    return jsonify({"status": "success"})

@app.route('/api/upload', methods=['POST'])
def upload():
    t, f = request.form.get("token"), request.files['image'].read()
    h = get_h(t)
    r1 = requests.post(API_URL, json={"operationName":"uploadMedia","variables":{"input":{"type":"IMAGE","provider":"S3"}},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_UPLOAD}}}, headers=h).json()
    requests.put(r1['data']['uploadMedia']['uploadUrl'], data=f)
    r3 = requests.post(API_URL, json={"operationName":"uploadMedia","variables":{"input":{"type":"IMAGE","provider":"S3","externalId":r1['data']['uploadMedia']['uploadUrl'].split('/')[-1].split('?')[0]}},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_UPLOAD}}}, headers=h).json()
    return jsonify({"mediaId": r3['data']['uploadMedia']['mediaId']})

@app.route('/api/delete_task', methods=['POST'])
def del_task():
    requests.post(API_URL, json={"operationName":"deleteTask","variables":{"id":request.json.get("id")},"extensions":{"persistedQuery":{"version":1,"sha256Hash":"48356f1577793d567c29379858369ce321a6e78336558ec50f0c23178401496e"}}}, headers=get_h(request.json.get("token")))
    return jsonify({"status": "success"})

@app.route('/api/credits', methods=['POST'])
def credits():
    r = requests.get(API_URL, params={"operationName":"getMyQuota","variables":"{}","extensions":json.dumps({"persistedQuery":{"version":1,"sha256Hash":H_CRE}})}, headers=get_h(request.json.get("token"))).json()
    return jsonify({"credits": r['data']['me']['quotaAmount']})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
