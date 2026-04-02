import requests, time, json, re, os
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ================= MASTER CONFIGURATION (EXACT HASHES) =================
API_URL = "https://api.pixai.art/graphql"
H_GEN    = "c057ef74858702d0205b68aa2c7701ac9d7882e288c9b01e3689e21757aef1f7"
H_POLL   = "6db0f9052ef7c760025083d34defa39cbc301029a89a893437a0da22171f74b8"
H_LORA   = "2f246fd8c1b73ed398eb4ccce2cfe08d0d502efb72ac08ad9a30e0a6ea17c090"
H_LIST   = "cc067203ddd0846c19d9e247d837c32da498247ec252fe30828434f2f136f53d"
H_UPLOAD = "dd71971acde11807d01862ff1a94657479f7e833af75eac850aa2de0a14fa1fa"
H_CRE    = "9356b42a4ff6e987347a1f1ee3de7aba4bd103b1cdbfbbc4c5c5fcf52767ad66"
H_SEARCH = "4d76952c681f7d0787077ddeec310f6475ab059e50546248120617abfb4031e9"
H_MODEL_SEARCH = "1658f8e716184e95d3177d20fad189d8f7b250fb30e8401496ed0aaf34e4ad83"

def get_h(t): 
    return {
        "Authorization": f"Bearer {t.strip()}", 
        "Content-Type": "application/json", 
        "x-browser-id": "cb8f9647d95c6f5309648829957c0a3d", 
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Mobile Safari/537.36"
    }

def clean_txt(text):
    return re.sub(r'[_*`\[\]()~>#+\-={}|.!]', '', str(text)) if text else ""

@app.route('/api/lora_meta', methods=['POST'])
def lora_meta():
    d = request.json
    p = {"operationName": "getGenerationModel", "variables": json.dumps({"id": d.get("id")}), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_LORA}})}
    try:
        res = requests.get(API_URL, params=p, headers=get_h(d.get("token")), timeout=10).json()
        v = res['data']['generationModel']['latestAvailableVersion']
        return jsonify({"v_id": v['id'], "trigger": v['extra'].get('triggerWords', ""), "name": res['data']['generationModel']['title'], "id": d.get("id")})
    except: return jsonify({"error": "not found"})

@app.route('/api/generate', methods=['POST'])
def generate():
    d = request.json
    token, prompt = d.get("token"), d.get("prompt")
    lora_configs = d.get("lora_configs", [])
    
    # FIX: Uses the Model ID you actually selected on the web
    modelId = d.get("modelId", "1861558740588989558") 
    helper = d.get("helper", True)

    batch, mediaId, strength = int(d.get("batch", 1)), d.get("mediaId"), float(d.get("strength", 0.55))
    width, height = int(d.get("w", 832)), int(d.get("h", 1248))
    steps, cfg, neg = int(d.get("steps", 28)), float(d.get("cfg", 12.7)), d.get("neg", "")

    l_w, l_p, all_t = {}, [], ""
    for conf in lora_configs:
        vid, wgt, trg = conf['v_id'], float(conf['weight']), conf['triggers']
        l_w[vid] = wgt
        all_t += f"{trg}, "
        l_p.append({"versionId": vid, "weight": wgt, "triggerWords": trg, "positionInfo": {"startIndex": 0, "endIndex": 0}})

    payload = {
        "operationName": "createGenerationTask",
        "variables": {
            "parameters": {
                "prompts": prompt + ", " + all_t, "negativePrompts": neg,
                "modelId": modelId, "width": width, "height": height, "batchSize": batch,
                "lora": l_w, "loraParameters": l_p, "mediaId": mediaId, "strength": strength,
                "samplingSteps": steps, "samplingMethod": "Euler a", "cfgScale": cfg,
                "promptHelper": {"withStage": helper, "userWantToEnable": helper, "enable": helper}
            },
            "extra": {"naturalPrompts": [prompt]} # Bypass Metadata
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

@app.route('/api/tasks', methods=['POST'])
def tasks():
    d = request.json
    p = {"operationName": "listMyTasks", "variables": json.dumps({"last": 30, "before": d.get("cursor"), "parameterFields": ["extra", "prompts", "negativePrompts", "samplingSteps", "samplingMethod", "cfgScale", "modelId"]}), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_LIST}})}
    try:
        r = requests.get(API_URL, params=p, headers=get_h(d.get("token"))).json()
        edges = r.get('data', {}).get('me', {}).get('tasks', {}).get('edges', [])
        task_data = []
        for edge in reversed(edges):
            node = edge.get('node', {})
            if node.get('status') == "completed":
                img = node.get('media', {}).get('urls', [{}])[0].get('url')
                # FIX: Find the original clean prompt from naturalPrompts
                params = node.get('parameters', {})
                extra = params.get('extra', {})
                original = extra.get('naturalPrompts', [""])[0]
                final = params.get('prompts', "")
                
                if img: 
                    task_data.append({
                        "url": img, 
                        "p_orig": clean_txt(original if original else final), 
                        "p_final": clean_txt(final),
                        "neg": params.get('negativePrompts', ""),
                        "steps": params.get('samplingSteps', ""),
                        "cfg": params.get('cfgScale', ""),
                        "method": params.get('samplingMethod', ""),
                        "id": node.get('id')
                    })
        page = r['data']['me']['tasks']['pageInfo']
        return jsonify({"status": "success", "tasks": task_data, "cursor": page['startCursor'] if page['hasPreviousPage'] else None})
    except: return jsonify({"status": "error"})

@app.route('/api/search_models', methods=['POST'])
def search_models():
    d = request.json
    v = {"keyword": d.get("keyword"), "feed": "meilisearch", "types": ["ANY_MODEL"], "first": 30, "after": d.get("cursor")}
    p = {"operationName": "listGenerationModels", "variables": json.dumps(v), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_MODEL_SEARCH}})}
    try:
        res = requests.get(API_URL, params=p, headers=get_h(d.get("token"))).json()
        items = [{"name": e['node']['title'], "id": e['node']['id'], "thumb": next((u['url'] for u in e['node']['media']['urls'] if u['variant'] == "STILL_THUMBNAIL"), "")} for e in res['data']['generationModels']['edges']]
        return jsonify({"results": items, "cursor": res['data']['generationModels']['pageInfo']['endCursor'] if res['data']['generationModels']['pageInfo']['hasNextPage'] else None})
    except: return jsonify({"error": "failed"})

@app.route('/api/upload', methods=['POST'])
def upload():
    t, f = request.form.get("token"), request.files['image'].read()
    h = get_h(t)
    try:
        r1 = requests.post(API_URL, json={"operationName":"uploadMedia","variables":{"input":{"type":"IMAGE","provider":"S3"}},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_UPLOAD}}}, headers=h).json()
        requests.put(r1['data']['uploadMedia']['uploadUrl'], data=f)
        ext_id = r1['data']['uploadMedia']['uploadUrl'].split('/')[-1].split('?')[0]
        r3 = requests.post(API_URL, json={"operationName":"uploadMedia","variables":{"input":{"type":"IMAGE","provider":"S3","externalId":ext_id}},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_UPLOAD}}}, headers=h).json()
        return jsonify({"status": "success", "mediaId": r3['data']['uploadMedia']['mediaId']})
    except: return jsonify({"status": "error"})

@app.route('/api/credits', methods=['POST'])
def credits():
    r = requests.get(API_URL, params={"operationName":"getMyQuota","variables":"{}","extensions":json.dumps({"persistedQuery":{"version":1,"sha256Hash":H_CRE}})}, headers=get_h(request.json.get("token"))).json()
    return jsonify({"credits": r['data']['me']['quotaAmount']})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
