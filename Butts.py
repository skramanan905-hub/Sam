import requests, time, json, re, os
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ================= MASTER CONFIGURATION (AUG 28) =================
API_URL = "https://api.pixai.art/graphql"
DAILY_URL = "https://api.pixai.art/v2/claim/pixai-daily-credits"
REST_FOLLOW_URL = "https://api.pixai.art/v2/quest-v2/report-social-follow"
REST_VISIT_URL = "https://api.pixai.art/v2/quest-v2/report-visit"

# UPDATED HASHES FROM AUG 27/28 LOGS
H_GEN    = "7662bf96848c0cd1e03cafc5a6b61785481a55a1c92faec3a248da9195bf9d25"
H_POLL   = "2526f64c73c59fcfeff938b0f4a8b3b610f2294bc6eb6b6b281aa671ac81a08e"
H_LIST   = "9b2cf8d56a4a7edd3db0e40c753cf35314edec9d335ed4f596592080e621758a"
H_SEARCH = "b7a2d663bc0381dd6eb26f8c68f702cb928bea720982f6f5553ea1629a8e871d"
H_META   = "cd94c1ebc6c2ee3bb3c10e1cb7c80cbd05c4470094b10e48a539aaaf36879696"

H_CRE    = "9356b42a4ff6e987347a1f1ee3de7aba4bd103b1cdbfbbc4c5c5fcf52767ad66"
H_ROLL   = "f0778d88963cc4e40749a8ecd9d510808b4a14cd63fac498e7763e6d5d780e5e"
H_UPLOAD = "dd71971acde11807d01862ff1a94657479f7e833af75eac850aa2de0a14fa1fa"
H_18PLUS = "fb22173aa2a43ff08be4221a17094a1445cb212e1b1970a1cee8c37e98d38304"

def get_h(t): 
    return {"Authorization": f"Bearer {t.strip()}", "Content-Type": "application/json", "x-browser-id": "56e77fe10bfcfb337ef2d43bc0df330f", "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36", "Accept": "application/graphql-response+json,application/json;q=0.9"}

def clean_txt(text):
    if not text or text == "null" or text == "None": return "N/A"
    return re.sub(r'[_*`\[\]()~>#+\-={}|.!]', '', str(text))

def format_pixai_time(ts):
    try:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ")
        return dt.strftime("%b %d, %I:%M %p")
    except: return ts

def fmt_num(num):
    if not num: return "0"
    num = int(num)
    if num >= 1000000: return f"{num/1000000:.1f}m"
    if num >= 1000: return f"{num/1000:.1f}k"
    return str(num)

def check_refresh(resp):
    new_t = resp.cookies.get("user_token")
    return new_t if new_t else None

@app.route('/')
def index(): return "Active"

@app.route('/api/restart', methods=['POST'])
def restart(): os._exit(1)

# ================= NEW SEARCH LOGIC =================
@app.route('/api/search', methods=['POST'])
def search_unified():
    d = request.json
    stype = d.get("type", "ANY_LORA")
    v = {"first": 36, "types": [stype], "feed": d.get("feed", "meilisearch"), "keyword": d.get("keyword", ""), "after": d.get("cursor")}
    if stype == "ANY_LORA": v["loraBaseModelTypes"] = ["SDXL_MODEL"]
    params = {"operationName": "listGenerationModels", "variables": json.dumps(v), "extensions": json.dumps({"clientLibrary": {"name": "@apollo/client", "version": "4.1.4"}, "persistedQuery": {"version": 1, "sha256Hash": H_SEARCH}})}
    r = requests.get(API_URL, params=params, headers=get_h(d.get("token")))
    res = r.json()
    items = []
    edges = res.get('data', {}).get('generationModels', {}).get('edges', [])
    for e in edges:
        n = e['node']
        thumb = next((u['url'] for u in n['media']['urls'] if u['variant'] == "STILL_THUMBNAIL"), n['media']['urls'][0]['url']) if n.get('media') else ""
        items.append({"name": n['title'], "id": n['id'], "thumb": thumb, "usage": fmt_num(n.get('refCount')), "likes": fmt_num(n.get('likedCount'))})
    page = res.get('data', {}).get('generationModels', {}).get('pageInfo', {})
    return jsonify({"results": items, "cursor": page.get('endCursor') if page.get('hasNextPage') else None, "refreshed_token": check_refresh(r)})

@app.route('/api/lora_meta', methods=['POST'])
def lora_meta():
    d = request.json
    params = {"operationName": "getGenerationModel", "variables": json.dumps({"id": d.get("id")}), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_META}})}
    r = requests.get(API_URL, params=params, headers=get_h(d.get("token")))
    res = r.json()
    if 'errors' in res or not res.get('data'): return jsonify({"status": "error", "raw": res})
    data = res['data']['generationModel']
    v = data['latestAvailableVersion']
    return jsonify({"v_id": v['id'], "trigger": v['extra'].get('triggerWords', ""), "name": data['title'], "id": d.get("id"), "refreshed_token": check_refresh(r)})

# ================= GENERATION & DETAILED HISTORY =================
@app.route('/api/generate', methods=['POST'])
def generate():
    d = request.json
    lora_configs = d.get("lora_configs", [])
    l_w, l_p, all_t = {}, [], ""
    for conf in lora_configs:
        vid, wgt, trg = conf['v_id'], float(conf['weight']), conf['triggers']
        l_w[vid] = wgt; all_t += f"{trg}, "; l_p.append({"versionId": vid, "weight": wgt, "triggerWords": trg, "positionInfo": {"startIndex": 0, "endIndex": 0}})
    
    payload = {"operationName": "createGenerationTask", "variables": {"parameters": {"prompts": d.get("prompt") + ", " + all_t, "negativePrompts": d.get("neg", ""), "modelId": d.get("modelId"), "width": int(d.get("w", 832)), "height": int(d.get("h", 1248)), "batchSize": int(d.get("batch", 1)), "seed": "", "priority": 1000, "lora": l_w, "loraParameters": l_p, "mediaId": d.get("mediaId"), "strength": float(d.get("strength", 0.55)), "samplingSteps": int(d.get("steps", 28)), "samplingMethod": "Euler a", "cfgScale": float(d.get("cfg", 12.7)), "promptHelper": {"withStage": True, "userWantToEnable": True, "enable": True}}, "extra": {"naturalPrompts": str(d.get("prompt"))}}, "extensions": {"clientLibrary": {"name": "@apollo/client", "version": "4.1.4"}, "persistedQuery": {"version": 1, "sha256Hash": H_GEN}}}
    r = requests.post(API_URL, json=payload, headers=get_h(d.get("token")))
    res_raw = r.json()
    if 'errors' in res_raw: return jsonify({"status": "error", "raw": res_raw})
    return jsonify({"status": "started", "tid": res_raw['data']['createGenerationTask']['id'], "req_log": payload, "raw": res_raw})

@app.route('/api/check_task', methods=['POST'])
def check_task():
    d = request.json
    p = {"operationName":"getTaskById","variables":json.dumps({"id":d.get("tid")}),"extensions":json.dumps({"persistedQuery":{"version":1,"sha256Hash":H_POLL}})}
    r = requests.get(API_URL, params=p, headers=get_h(d.get("token")))
    sr = r.json()
    status = sr.get('data', {}).get('task', {}).get('status', 'error')
    return jsonify({"status": status, "raw": sr, "images": [i['url'] for i in sr['data']['task']['media']['urls'] if i['variant'] == "PUBLIC"] if status == "completed" else [], "refreshed_token": check_refresh(r)})

@app.route('/api/tasks', methods=['POST'])
def tasks():
    d = request.json
    vars = {"last": 30, "before": d.get("cursor")}
    # Updated mapping for listMyTasksTyped
    p = {"operationName": "listMyTasksTyped", "variables": json.dumps(vars), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_LIST}})}
    r = requests.get(API_URL, params=p, headers=get_h(d.get("token")))
    resp_json = r.json()
    task_data = []
    edges = resp_json.get('data', {}).get('me', {}).get('tasks', {}).get('edges', [])
    for edge in reversed(edges):
        node = edge['node']
        if node.get('status') == "completed" and node.get('media'):
            # PIXAI DETAILED EXTRACTION
            p_node = node.get('parameters', {}) or node.get('typedParameters', {})
            extra = p_node.get('extra', {})
            orig_prompt = extra.get('naturalPrompts', "N/A")
            
            task_data.append({
                "url": node['media']['urls'][0]['url'], 
                "p_orig": clean_txt(orig_prompt), 
                "p_final": clean_txt(p_node.get('prompts')), 
                "neg": clean_txt(p_node.get('negativePrompts', "None")), 
                "id": node['id'], 
                "time": format_pixai_time(node.get('createdAt')), 
                "size": f"{p_node.get('width', '???')}x{p_node.get('height', '???')}", 
                "steps": p_node.get('samplingSteps', '??'), 
                "cfg": p_node.get('cfgScale', '??'),
                "ref_url": f"https://api.pixai.art/v1/media/{p_node.get('mediaId')}/thumbnail" if p_node.get('mediaId') else None,
                "loras": [{"t": l.get('triggerWords'), "w": l.get('weight')} for l in p_node.get('loraParameters', [])]
            })
    return jsonify({"status": "success", "tasks": task_data, "cursor": resp_json['data']['me']['tasks']['pageInfo']['startCursor'], "refreshed_token": check_refresh(r)})

# ================= ALL CLAIM TOOLS =================
@app.route('/api/daily_claim', methods=['POST'])
def daily_claim():
    r = requests.post(DAILY_URL, headers=get_h(request.json.get("token")), data="")
    return jsonify({"status": "success", "raw": r.text, "refreshed_token": check_refresh(r)})

@app.route('/api/credits', methods=['POST'])
def credits():
    p = {"operationName":"getMyQuota","variables":"{}","extensions":json.dumps({"persistedQuery":{"version":1,"sha256Hash":H_CRE}})}
    r = requests.get(API_URL, params=p, headers=get_h(request.json.get("token")))
    return jsonify({"credits": r.json()['data']['me']['quotaAmount'], "refreshed_token": check_refresh(r)})

@app.route('/api/claim_old', methods=['POST'])
def claim_old():
    h, tl = get_h(request.json.get("token")), []
    q = "mutation followSocialMedia($platform: String!) { followSocialMedia(platform: $platform) { success __typename } }"
    for p in ["tiktok", "youtube", "instagram", "twitter", "discord"]:
        r = requests.post(API_URL, json={"operationName":"followSocialMedia","variables":{"platform":p},"query":q}, headers=h)
        tl.append({p: r.text}); time.sleep(1)
    return jsonify({"status": "success", "raw": tl})

@app.route('/api/claim_new', methods=['POST'])
def claim_new():
    h, tl = get_h(request.json.get("token")), []
    for p in ["tiktok", "youtube", "instagram", "twitter", "discord"]:
        r = requests.post(REST_FOLLOW_URL, json={"platform": p}, headers=h)
        tl.append({p: r.text}); time.sleep(1)
    return jsonify({"status": "success", "raw": tl})

@app.route('/api/claim_visits', methods=['POST'])
def claim_visits():
    h, tl = get_h(request.json.get("token")), []
    for u in ["https://youtu.be/nFJoUWvs0ko?si=YvjDeXw5hixETOR8", "https://pixai.art/tsubaki-2"]:
        r = requests.post(REST_VISIT_URL, json={"url": u}, headers=h)
        tl.append({u: r.text}); time.sleep(1)
    return jsonify({"status": "success", "raw": tl})

@app.route('/api/claim_mios', methods=['POST'])
def claim_mios():
    h, tl = get_h(request.json.get("token")), []
    r1 = requests.post(API_URL, json={"operationName":"rollAprilFools2026Lottery","variables":{},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_ROLL}}}, headers=h)
    tl.append({"lottery": r1.text})
    for i in range(3226, 3235):
        r_t = requests.post(f"https://api.pixai.art/v2/event/aprilFoolsEvent2026/tier-rewards/{i}/claim", headers=h, data="")
        tl.append({f"tier_{i}": r_t.status_code}); time.sleep(0.5)
    return jsonify({"status": "success", "raw": tl})

@app.route('/api/enable_18', methods=['POST'])
def enable_18():
    h = get_h(request.json.get("token"))
    r = requests.post(API_URL, json={"operationName":"setPreferences","variables":{"value":{"ageVerificationStatus":"OVER18"}},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_18PLUS}}}, headers=h)
    return jsonify({"status": "success", "raw": r.text})

@app.route('/api/upload', methods=['POST'])
def upload():
    t, f = request.form.get("token"), request.files['image'].read()
    r1 = requests.post(API_URL, json={"operationName":"uploadMedia","variables":{"input":{"type":"IMAGE","provider":"S3"}},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_UPLOAD}}}, headers=get_h(t)).json()
    requests.put(r1['data']['uploadMedia']['uploadUrl'], data=f)
    ext_id = r1['data']['uploadMedia']['uploadUrl'].split('/')[-1].split('?')[0]
    r3 = requests.post(API_URL, json={"operationName":"uploadMedia","variables":{"input":{"type":"IMAGE","provider":"S3","externalId":ext_id}},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_UPLOAD}}}, headers=get_h(t)).json()
    return jsonify({"success": True, "mediaId": r3['data']['uploadMedia']['mediaId']})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
