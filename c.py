import requests, time, json, re, os
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ================= MASTER CONFIGURATION =================
API_URL = "https://api.pixai.art/graphql"
H_GEN    = "61b5dafa7ade64f847051cdca7024b359bae652421834b8f78423d7640f17d96"
H_POLL   = "a32947c6b546befddacd08a3af63cc4ee2277af27fd43342a01fc0414fca3e8a"
H_LORA   = "4e1614f7373d676cb8ec17975796188369ce321a6e78336558ec50f0c2317840"
H_ROLL   = "f0778d88963cc4e40749a8ecd9d510808b4a14cd63fac498e7763e6d5d780e5e"
H_REW    = "923002464a8e816706394061c18316cd2d14f5f025dbd1d08020e44cd8a23546"
H_CRE    = "9356b42a4ff6e987347a1f1ee3de7aba4bd103b1cdbfbbc4c5c5fcf52767ad66"
H_LIST   = "cc067203ddd0846c19d9e247d837c32da498247ec252fe30828434f2f136f53d"
H_SEARCH = "4d76952c681f7d0787077ddeec310f6475ab059e50546248120617abfb4031e9"
H_MODEL_SEARCH = "1658f8e716184e95d3177d20fad189d8f7b250fb30e8401496ed0aaf34e4ad83"

def get_h(t): 
    return {"Authorization": f"Bearer {t.strip()}", "Content-Type": "application/json", "x-browser-id": "08df9bc9358ad97ebfe0ac86284587e5", "User-Agent": "Mozilla/5.0 (Linux; Android 15; I2301) AppleWebKit/537.36"}

def clean_txt(text):
    return re.sub(r'[_*`\[\]()~>#+\-={}|.!]', '', str(text)) if text else ""

@app.route('/api/lora_meta', methods=['POST'])
def lora_meta():
    d = request.json
    p = {"operationName": "getGenerationModel", "variables": json.dumps({"id": d.get("id")}), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_LORA}})}
    try:
        res = requests.get(API_URL, params=p, headers=get_h(d.get("token")), timeout=10).json()
        v = res['data']['generationModel']['latestAvailableVersion']
        return jsonify({"v_id": v['id'], "trigger": v['extra'].get('triggerWords', ""), "name": res['data']['generationModel']['title']})
    except: return jsonify({"error": "not found"})

@app.route('/api/generate', methods=['POST'])
def generate():
    d = request.json
    token, prompt, lora_configs = d.get("token"), d.get("prompt"), d.get("lora_configs", [])
    modelId = d.get("modelId", "1861558740588989558")
    batch, mediaId, strength = int(d.get("batch", 1)), d.get("mediaId"), float(d.get("strength", 0.55))
    width, height = int(d.get("w", 832)), int(d.get("h", 1248))
    steps, cfg, neg = int(d.get("steps", 28)), float(d.get("cfg", 12.7)), d.get("neg", "")

    l_w, l_p, all_t = {}, [], ""
    for conf in lora_configs:
        vid, wgt, trg = conf['v_id'], float(conf['weight']), conf['triggers']
        l_w[vid] = wgt; all_t += f"{trg}, "; l_p.append({"versionId": vid, "weight": wgt, "triggerWords": trg, "positionInfo": {"startIndex": 0, "endIndex": 0}})

    payload = {"operationName": "createGenerationTask", "variables": {"parameters": {"prompts": prompt + ", " + all_t, "negativePrompts": neg, "modelId": modelId, "width": width, "height": height, "batchSize": batch, "lora": l_w, "loraParameters": l_p, "mediaId": mediaId, "strength": strength, "samplingSteps": steps, "samplingMethod": "Euler a", "cfgScale": cfg, "promptHelper": {"withStage": True, "userWantToEnable": True, "enable": True}}}, "extra": {"naturalPrompts": [prompt]}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_GEN}}}
    try:
        res = requests.post(API_URL, json=payload, headers=get_h(token)).json()
        tid = res['data']['createGenerationTask']['id']
        for _ in range(30):
            time.sleep(15) # REVERTED TO 15 SECONDS
            sr = requests.get(API_URL, params={"operationName":"getTaskById","variables":json.dumps({"id":tid}),"extensions":json.dumps({"persistedQuery":{"version":1,"sha256Hash":H_POLL}})}, headers=get_h(token)).json()
            if sr['data']['task']['status'] == "completed":
                return jsonify({"status": "success", "images": [i['url'] for i in sr['data']['task']['media']['urls'] if i['variant'] == "PUBLIC"]})
        return jsonify({"status": "error"})
    except: return jsonify({"status": "error"})

@app.route('/api/tasks', methods=['POST'])
def tasks():
    d = request.json
    p = {"operationName": "listMyTasks", "variables": json.dumps({"last": 30, "before": d.get("cursor"), "parameterFields": ["extra", "prompts", "negativePrompts", "samplingSteps", "samplingMethod", "cfgScale", "width", "height", "modelId"]}), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_LIST}})}
    try:
        r = requests.get(API_URL, params=p, headers=get_h(d.get("token"))).json()
        edges = r.get('data', {}).get('me', {}).get('tasks', {}).get('edges', [])
        task_data = []
        for edge in reversed(edges):
            node = edge.get('node', {})
            if node.get('status') == "completed":
                img = node.get('media', {}).get('urls', [{}])[0].get('url')
                params = node.get('parameters', {})
                original = params.get('extra', {}).get('naturalPrompts', [""])[0]
                final = params.get('prompts', "")
                task_data.append({"url": img, "p_orig": clean_txt(original if original else final), "p_final": clean_txt(final), "neg": params.get('negativePrompts', ""), "steps": params.get('samplingSteps', ""), "cfg": params.get('cfgScale', ""), "method": params.get('samplingMethod', ""), "size": f"{params.get('width')}x{params.get('height')}", "id": node.get('id'), "model": params.get('modelId', "Unknown")})
        page = r['data']['me']['tasks']['pageInfo']
        return jsonify({"status": "success", "tasks": task_data, "cursor": page['startCursor'] if page['hasPreviousPage'] else None})
    except: return jsonify({"status": "error"})

@app.route('/api/search_models', methods=['POST'])
def search_models():
    d = request.json
    v = {"keyword": d.get("keyword"), "feed": "meilisearch", "types": ["ANY_MODEL"], "first": 30, "after": d.get("cursor")}
    p = {"operationName": "listGenerationModels", "variables": json.dumps(v), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_MODEL_SEARCH}})}
    res = requests.get(API_URL, params=p, headers=get_h(d.get("token"))).json()
    items = [{"name": e['node']['title'], "id": e['node']['latestAvailableVersion']['id'], "thumb": next((u['url'] for u in e['node']['media']['urls'] if u['variant'] == "STILL_THUMBNAIL"), "")} for e in res['data']['generationModels']['edges']]
    return jsonify({"results": items, "cursor": res['data']['generationModels']['pageInfo']['endCursor'] if res['data']['generationModels']['pageInfo']['hasNextPage'] else None})

@app.route('/api/search', methods=['POST'])
def search_loras():
    d = request.json
    v = {"keyword": d.get("keyword"), "feed": "meilisearch", "types": ["ANY_LORA"], "first": 30, "after": d.get("cursor")}
    r = requests.get(API_URL, params={"operationName":"listGenerationModels","variables":json.dumps(v),"extensions":json.dumps({"persistedQuery":{"version":1,"sha256Hash":H_SEARCH}})}, headers=get_h(d.get("token"))).json()
    items = [{"name": e['node']['title'], "id": e['node']['id'], "thumb": next((u['url'] for u in e['node']['media']['urls'] if u['variant'] == "STILL_THUMBNAIL"), "")} for e in r['data']['generationModels']['edges']]
    return jsonify({"results": items, "cursor": r['data']['generationModels']['pageInfo']['endCursor'] if r['data']['generationModels']['pageInfo']['hasNextPage'] else None})

@app.route('/api/claim', methods=['POST'])
def claim():
    h = get_h(request.json.get("token"))
    requests.post(API_URL, json={"operationName":"rollAprilFools2026Lottery","variables":{},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_ROLL}}}, headers=h)
    for p in ["tiktok", "youtube", "instagram", "twitter", "discord"]:
        requests.post(API_URL, json={"operationName":"followSocialMedia","variables":{"platform":p},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_REW}}}, headers=h)
    return jsonify({"status": "success"})

@app.route('/api/credits', methods=['POST'])
def credits():
    r = requests.get(API_URL, params={"operationName":"getMyQuota","variables":"{}","extensions":json.dumps({"persistedQuery":{"version":1,"sha256Hash":H_CRE}})}, headers=get_h(request.json.get("token"))).json()
    return jsonify({"credits": r['data']['me']['quotaAmount']})

@app.route('/api/upload', methods=['POST'])
def upload():
    t, f = request.form.get("token"), request.files['image'].read()
    h = get_h(t)
    r1 = requests.post(API_URL, json={"operationName":"uploadMedia","variables":{"input":{"type":"IMAGE","provider":"S3"}},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_UPLOAD}}}, headers=h).json()
    requests.put(r1['data']['uploadMedia']['uploadUrl'], data=f); ext_id = r1['data']['uploadMedia']['uploadUrl'].split('/')[-1].split('?')[0]
    r3 = requests.post(API_URL, json={"operationName":"uploadMedia","variables":{"input":{"type":"IMAGE","provider":"S3","externalId":ext_id}},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_UPLOAD}}}, headers=h).json()
    return jsonify({"status": "success", "mediaId": r3['data']['uploadMedia']['mediaId']})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
