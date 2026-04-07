import requests, time, json, re, os
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ================= MASTER CONFIGURATION =================
API_URL = "https://api.pixai.art/graphql"
DAILY_URL = "https://api.pixai.art/v2/claim/pixai-daily-credits"

H_GEN    = "61b5dafa7ade64f847051cdca7024b359bae652421834b8f78423d7640f17d96"
H_POLL   = "a32947c6b546befddacd08a3af63cc4ee2277af27fd43342a01fc0414fca3e8a"
H_LORA   = "4e1614f7373d676cb8ec17975796188369ce321a6e78336558ec50f0c2317840"
H_ROLL   = "f0778d88963cc4e40749a8ecd9d510808b4a14cd63fac498e7763e6d5d780e5e"
H_REW    = "923002464a8e816706394061c18316cd2d14f5f025dbd1d08020e44cd8a23546"
H_CRE    = "9356b42a4ff6e987347a1f1ee3de7aba4bd103b1cdbfbbc4c5c5fcf52767ad66"
H_LIST   = "cc067203ddd0846c19d9e247d837c32da498247ec252fe30828434f2f136f53d"
H_UPLOAD = "dd71971acde11807d01862ff1a94657479f7e833af75eac850aa2de0a14fa1fa"
H_SEARCH = "4d76952c681f7d0787077ddeec310f6475ab059e50546248120617abfb4031e9"
H_MODEL_SEARCH = "1658f8e716184e95d3177d20fad189d8f7b250fb30e8401496ed0aaf34e4ad83"
H_COST   = "50567e9680327f27a692e76f62b1b3699b24467f3747b0e14d3345d2e3077395"

def get_h(t): 
    return {"Authorization": f"Bearer {t.strip()}", "Content-Type": "application/json", "x-browser-id": "08df9bc9358ad97ebfe0ac86284587e5", "User-Agent": "Mozilla/5.0 (Linux; Android 15; I2301) AppleWebKit/537.36"}

def clean_txt(text):
    if not text or text == "null": return "None"
    return re.sub(r'[_*`\[\]()~>#+\-={}|.!]', '', str(text))

def format_pixai_time(ts):
    try:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ")
        return dt.strftime("%b %d, %Y %I:%M %p")
    except: return ts

def fmt_num(num):
    if not num: return "0"
    if num >= 1000000: return f"{num/1000000:.2f}m"
    if num >= 1000: return f"{num/1000:.2f}k"
    return str(num)

def fmt_type(t):
    mapping = {"SDXL_MODEL": "PixAI XL", "DIT7B_MODEL": "PixAI DiT.1", "MMDIT26A_MODEL": "PixAI DiT.2", "CHAT": "Edit"}
    return mapping.get(t, "Model")

def check_refresh(resp):
    new_t = resp.cookies.get("user_token")
    return new_t if new_t else None

@app.route('/')
def index():
    return "Active"

@app.route('/api/daily_claim', methods=['POST'])
def daily_claim():
    t = request.json.get("token")
    try:
        r = requests.post(DAILY_URL, headers=get_h(t), data="")
        return jsonify({"status": "success", "msg": r.text, "refreshed_token": check_refresh(r)})
    except: return jsonify({"status": "error"})

@app.route('/api/compute_cost', methods=['POST'])
def compute_cost():
    d = request.json
    t = d.get("token")
    l_w = {c['v_id']: float(c['weight']) for c in d.get("lora_configs", [])}
    vars = {"parameters": {"modelId": d.get("modelId"), "width": int(d.get("w")), "height": int(d.get("h")), "batchSize": int(d.get("batch")), "lora": l_w, "samplingSteps": int(d.get("steps")), "priority": 1000}}
    payload = {"operationName": "computeTaskCost", "variables": vars, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_COST}}}
    try:
        r = requests.post(API_URL, json=payload, headers=get_h(t))
        return jsonify({"cost": r.json()['data']['computeTaskCost']['cost']})
    except: return jsonify({"cost": 0})

@app.route('/api/tasks', methods=['POST'])
def tasks():
    d = request.json
    t, cursor = d.get("token"), d.get("cursor")
    p_fields = ["extra", "prompts", "negativePrompts", "samplingSteps", "samplingMethod", "cfgScale", "width", "height", "loraParameters", "mediaId", "strength"]
    vars = {"last": 30, "before": cursor, "parameterFields": p_fields}
    p = {"operationName": "listMyTasks", "variables": json.dumps(vars), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_LIST}})}
    try:
        r = requests.get(API_URL, params=p, headers=get_h(t))
        resp_json = r.json()
        edges = resp_json['data']['me']['tasks']['edges']
        task_data = []
        for edge in reversed(edges):
            node = edge['node']
            if node['status'] == "completed":
                p_node = node['parameters']
                extra = p_node.get('extra', {})
                # --- UNTOUCHED HISTORY LOGIC ---
                natural_data = extra.get('naturalPrompts', [])
                if isinstance(natural_data, list) and len(natural_data) > 0: orig_prompt = natural_data[0]
                elif isinstance(natural_data, str) and len(natural_data) > 1: orig_prompt = natural_data
                else: orig_prompt = p_node.get('prompts', 'N/A')
                ref_id = p_node.get('mediaId')
                ref_thumb = f"https://api.pixai.art/v1/media/{ref_id}/thumbnail" if ref_id else None
                task_data.append({"url": node['media']['urls'][0]['url'], "p_orig": clean_txt(orig_prompt), "p_final": clean_txt(p_node.get('prompts')), "neg": clean_txt(p_node.get('negativePrompts', "")), "id": node['id'], "time": format_pixai_time(node.get('createdAt')), "size": f"{p_node.get('width')}x{p_node.get('height')}", "steps": p_node.get('samplingSteps'), "cfg": p_node.get('cfgScale'), "method": p_node.get('samplingMethod'), "ref_url": ref_thumb, "loras": [{"t": l.get('triggerWords'), "w": l.get('weight')} for l in p_node.get('loraParameters', [])]})
        page = resp_json['data']['me']['tasks']['pageInfo']
        return jsonify({"status": "success", "tasks": task_data, "cursor": page['startCursor'] if page['hasPreviousPage'] else None, "refreshed_token": check_refresh(r)})
    except: return jsonify({"status": "error"})

@app.route('/api/generate', methods=['POST'])
def generate():
    d = request.json
    token, prompt, modelId = d.get("token"), d.get("prompt"), d.get("modelId", "1861558740588989558")
    lora_configs = d.get("lora_configs", [])
    batch, mediaId, strength = int(d.get("batch", 1)), d.get("mediaId"), float(d.get("strength", 0.55))
    width, height = int(d.get("w", 832)), int(d.get("h", 1248))
    steps, cfg, neg = int(d.get("steps", 28)), float(d.get("cfg", 12.7)), d.get("neg", "")
    l_w, l_p, all_t = {}, [], ""
    for conf in lora_configs:
        vid, wgt, trg = conf['v_id'], float(conf['weight']), conf['triggers']
        l_w[vid] = wgt; all_t += f"{trg}, "; l_p.append({"versionId": vid, "weight": wgt, "triggerWords": trg, "positionInfo": {"startIndex": 0, "endIndex": 0}})
    payload = {"operationName": "createGenerationTask", "variables": {"parameters": {"prompts": prompt + ", " + all_t, "negativePrompts": neg, "modelId": modelId, "width": width, "height": height, "batchSize": batch, "lora": l_w, "loraParameters": l_p, "mediaId": mediaId, "strength": strength, "samplingSteps": steps, "samplingMethod": "Euler a", "cfgScale": cfg, "promptHelper": {"withStage": True, "userWantToEnable": True, "enable": True}}, "extra": {"naturalPrompts": [prompt]}}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_GEN}}}
    try:
        r_init = requests.post(API_URL, json=payload, headers=get_h(token))
        res = r_init.json()
        tid = res['data']['createGenerationTask']['id']
        while True: # UNTOUCHED POLLING
            time.sleep(15)
            r_poll = requests.get(API_URL, params={"operationName":"getTaskById","variables":json.dumps({"id":tid}),"extensions":json.dumps({"persistedQuery":{"version":1,"sha256Hash":H_POLL}})}, headers=get_h(token))
            sr = r_poll.json()
            if sr['data']['task']['status'] == "completed":
                return jsonify({"status": "success", "images": [i['url'] for i in sr['data']['task']['media']['urls'] if i['variant'] == "PUBLIC"], "refreshed_token": check_refresh(r_poll)})
            if sr['data']['task']['status'] == "failed": return jsonify({"status": "error"})
    except: return jsonify({"status": "error"})

@app.route('/api/search_models', methods=['POST'])
def search_models():
    d = request.json
    sort = d.get("sort", "most_used")
    v = {"keyword": d.get("keyword"), "feed": "preset" if sort == "trending" else "meilisearch", "sort": sort, "types": ["ANY_MODEL"], "first": 30, "after": d.get("cursor")}
    p = {"operationName": "listGenerationModels", "variables": json.dumps(v), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_MODEL_SEARCH}})}
    r = requests.get(API_URL, params=p, headers=get_h(d.get("token")))
    res = r.json()
    items = []
    for e in res['data']['generationModels']['edges']:
        n = e['node']
        items.append({"name": n['title'], "id": n['latestAvailableVersion']['id'] if n.get('latestAvailableVersion') else n['id'], "thumb": next((u['url'] for u in n['media']['urls'] if u['variant'] == "STILL_THUMBNAIL"), ""), "usage": fmt_num(n.get('refCount')), "likes": fmt_num(n.get('likedCount')), "type": fmt_type(n.get('type'))})
    return jsonify({"results": items, "cursor": res['data']['generationModels']['pageInfo']['endCursor'] if res['data']['generationModels']['pageInfo']['hasNextPage'] else None, "refreshed_token": check_refresh(r)})

@app.route('/api/search', methods=['POST'])
def search_loras():
    d = request.json
    sort = d.get("sort", "most_used")
    v = {"keyword": d.get("keyword"), "feed": "meilisearch", "sort": sort, "types": ["ANY_LORA"], "first": 30, "after": d.get("cursor")}
    r = requests.get(API_URL, params={"operationName":"listGenerationModels","variables":json.dumps(v),"extensions":json.dumps({"persistedQuery":{"version":1,"sha256Hash":H_SEARCH}})}, headers=get_h(d.get("token")))
    res = r.json()
    items = []
    for e in res['data']['generationModels']['edges']:
        n = e['node']
        items.append({"name": n['title'], "id": n['id'], "thumb": next((u['url'] for u in n['media']['urls'] if u['variant'] == "STILL_THUMBNAIL"), ""), "usage": fmt_num(n.get('refCount')), "likes": fmt_num(n.get('likedCount'))})
    return jsonify({"results": items, "cursor": res['data']['generationModels']['pageInfo']['endCursor'] if res['data']['generationModels']['pageInfo']['hasNextPage'] else None, "refreshed_token": check_refresh(r)})

@app.route('/api/lora_meta', methods=['POST'])
def lora_meta():
    d = request.json
    p = {"operationName": "getGenerationModel", "variables": json.dumps({"id": d.get("id")}), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_LORA}})}
    r = requests.get(API_URL, params=p, headers=get_h(d.get("token")))
    data = r.json()
    v = data['data']['generationModel']['latestAvailableVersion']
    return jsonify({"v_id": v['id'], "trigger": v['extra'].get('triggerWords', ""), "name": data['data']['generationModel']['title'], "id": d.get("id"), "refreshed_token": check_refresh(r)})

@app.route('/api/credits', methods=['POST'])
def credits():
    r = requests.get(API_URL, params={"operationName":"getMyQuota","variables":"{}","extensions":json.dumps({"persistedQuery":{"version":1,"sha256Hash":H_CRE}})}, headers=get_h(request.json.get("token")))
    return jsonify({"credits": r.json()['data']['me']['quotaAmount'], "refreshed_token": check_refresh(r)})

@app.route('/api/claim', methods=['POST'])
def claim():
    t = request.json.get("token")
    h = get_h(t)
    # 1. Lottery Roll
    requests.post(API_URL, json={"operationName":"rollAprilFools2026Lottery","variables":{},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_ROLL}}}, headers=h)
    # 2. 5 Social Follows
    for p in ["tiktok", "youtube", "instagram", "twitter", "discord"]:
        requests.post(API_URL, json={"operationName":"followSocialMedia","variables":{"platform":p},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_REW}}}, headers=h)
    # 3. FIXED: Milestone Tiers with correct JSON body
    for i in range(3226, 3235):
        requests.post(f"https://api.pixai.art/v2/event/aprilFoolsEvent2026/tier-rewards/{i}/claim", headers=h, json={})
        time.sleep(0.5)
    return jsonify({"status": "success"})

@app.route('/api/upload', methods=['POST'])
def upload():
    t, f = request.form.get("token"), request.files['image'].read()
    h = get_h(t)
    r1 = requests.post(API_URL, json={"operationName":"uploadMedia","variables":{"input":{"type":"IMAGE","provider":"S3"}},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_UPLOAD}}}, headers=h).json()
    requests.put(r1['data']['uploadMedia']['uploadUrl'], data=f)
    ext_id = r1['data']['uploadMedia']['uploadUrl'].split('/')[-1].split('?')[0]
    r3 = requests.post(API_URL, json={"operationName":"uploadMedia","variables":{"input":{"type":"IMAGE","provider":"S3","externalId":ext_id}},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_UPLOAD}}}, headers=h).json()
    return jsonify({"success": True, "mediaId": r3['data']['uploadMedia']['mediaId']})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
