import requests, time, json, re, os
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app) # Allows InfinityFree to talk to Render

# ================= CONFIGURATION (EXACTLY FROM YOUR CODE) =================
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

def get_h(t): 
    return {"Authorization": f"Bearer {t.strip()}", "Content-Type": "application/json", "x-browser-id": "cb8f9647d95c6f5309648829957c0a3d", "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36"}

def clean_txt(text):
    if not text: return ""
    return re.sub(r'[_*`\[\]()~>#+\-={}|.!]', '', str(text))

def fetch_lora_meta(token, lid):
    p = {"operationName": "getGenerationModel", "variables": json.dumps({"id": lid}), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_LORA}})}
    try:
        res = requests.get(API_URL, params=p, headers=get_h(token), timeout=10).json()
        v = res['data']['generationModel']['latestAvailableVersion']
        return {"v_id": v['id'], "trigger": v['extra'].get('triggerWords', "")}
    except: return None

# --- API ENDPOINTS ---

@app.route('/api/credits', methods=['POST'])
def balance():
    t = request.json.get("token")
    p = {"operationName": "getMyQuota", "variables": "{}", "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_CRE}})}
    try:
        r = requests.get(API_URL, params=p, headers=get_h(t), timeout=10).json()
        return jsonify({"status": "success", "credits": r['data']['me']['quotaAmount']})
    except: return jsonify({"status": "error"})

@app.route('/api/search', methods=['POST'])
def search():
    data = request.json
    t, kw, cursor = data.get("token"), data.get("keyword"), data.get("cursor")
    vars = {"keyword": kw, "feed": "meilisearch", "types": ["ANY_LORA"], "first": 30, "after": cursor}
    p = {"operationName": "listGenerationModels", "variables": json.dumps(vars), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_SEARCH}})}
    try:
        res = requests.get(API_URL, params=p, headers=get_h(t), timeout=20).json()
        data = res['data']['generationModels']
        results = []
        for edge in data['edges']:
            n = edge['node']
            thumb = next((u['url'] for u in n['media']['urls'] if u['variant'] == "STILL_THUMBNAIL"), None)
            results.append({"name": n['title'], "id": n['id'], "thumb": thumb})
        return jsonify({"status": "success", "results": results, "nextCursor": data['pageInfo']['endCursor'] if data['pageInfo']['hasNextPage'] else None})
    except: return jsonify({"status": "error"})

@app.route('/api/upload', methods=['POST'])
def upload():
    t = request.form.get("token")
    file = request.files['image'].read()
    try:
        h = get_h(t)
        r1 = requests.post(API_URL, json={"operationName":"uploadMedia","variables":{"input":{"type":"IMAGE","provider":"S3"}},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_UPLOAD}}}, headers=h).json()
        requests.put(r1['data']['uploadMedia']['uploadUrl'], data=file)
        ext_id = r1['data']['uploadMedia']['uploadUrl'].split('/')[-1].split('?')[0]
        r3 = requests.post(API_URL, json={"operationName":"uploadMedia","variables":{"input":{"type":"IMAGE","provider":"S3","externalId":ext_id}},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_UPLOAD}}}, headers=h).json()
        return jsonify({"status": "success", "mediaId": r3['data']['uploadMedia']['mediaId']})
    except: return jsonify({"status": "error"})

@app.route('/api/generate', methods=['POST'])
def generate():
    data = request.json
    token, prompt, loras = data.get("token"), data.get("prompt"), data.get("loras", [])
    batch, mid, strength = int(data.get("batch", 1)), data.get("mediaId"), float(data.get("strength", 0.55))
    
    weights, params, triggers = {}, [], ""
    for lid in loras:
        meta = fetch_lora_meta(token, lid)
        if meta:
            weights[meta['v_id']] = 0.7; triggers += f", {meta['trigger']}"
            params.append({"versionId": meta['v_id'], "weight": 0.7, "triggerWords": meta['trigger'], "positionInfo": {"startIndex": 0, "endIndex": 0}})
    
    payload = {"operationName": "createGenerationTask", "variables": {"parameters": {"prompts": prompt + triggers, "modelId": "1861558740588989558", "width": 512, "height": 1024, "batchSize": batch, "lora": weights, "loraParameters": params, "mediaId": mid, "strength": strength, "samplingSteps": 28, "samplingMethod": "Euler a", "cfgScale": 5, "promptHelper": {"withStage": True, "userWantToEnable": True, "enable": True}}}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_GEN}}}
    try:
        res = requests.post(API_URL, json=payload, headers=get_h(token), timeout=25).json()
        tid = res['data']['createGenerationTask']['id']
        for _ in range(20):
            time.sleep(15)
            sr = requests.get(API_URL, params={"operationName":"getTaskById","variables":json.dumps({"id":tid}),"extensions":json.dumps({"persistedQuery":{"version":1,"sha256Hash":H_POLL}})}, headers=get_h(token)).json()
            if sr['data']['task']['status'] == "completed":
                return jsonify({"status": "success", "images": [img['url'] for img in sr['data']['task']['media']['urls'] if img['variant'] == "PUBLIC"], "finalPrompt": prompt + triggers})
            if sr['data']['task']['status'] == "failed": break
        return jsonify({"status": "error", "message": "Task Failed or Timeout"})
    except: return jsonify({"status": "error"})

@app.route('/api/claim', methods=['POST'])
def claim():
    t = request.json.get("token")
    h = get_h(t)
    try:
        requests.post(API_URL, json={"operationName":"rollAprilFools2026Lottery","variables":{},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_ROLL}}}, headers=h)
        for p in ["tiktok", "youtube", "instagram", "twitter", "discord"]:
            requests.post(API_URL, json={"operationName":"followSocialMedia","variables":{"platform":p},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_REW}}}, headers=h)
        return jsonify({"status": "success"})
    except: return jsonify({"status": "error"})

@app.route('/api/tasks', methods=['POST'])
def tasks():
    t = request.json.get("token")
    try:
        r = requests.get(API_URL, params={"operationName":"listMyTasks","variables":json.dumps({"last":30,"parameterFields":["extra","prompts"]}),"extensions":json.dumps({"persistedQuery":{"version":1,"sha256Hash":H_LIST}})}, headers=get_h(t)).json()
        res = []
        for edge in r['data']['me']['tasks']['edges']:
            if edge['node']['status'] == "completed":
                res.append({"url": edge['node']['media']['urls'][0]['url'], "prompt": clean_txt(edge['node']['parameters']['prompts'])})
        return jsonify({"status": "success", "tasks": res})
    except: return jsonify({"status": "error"})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
