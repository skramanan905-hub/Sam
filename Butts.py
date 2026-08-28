import requests, time, json, re, os
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ================= MASTER CONFIGURATION (AUG 28 UPDATED) =================
API_URL = "https://api.pixai.art/graphql"
DAILY_URL = "https://api.pixai.art/v2/claim/pixai-daily-credits"
REST_FOLLOW_URL = "https://api.pixai.art/v2/quest-v2/report-social-follow"
REST_VISIT_URL = "https://api.pixai.art/v2/quest-v2/report-visit"

# UPDATED HASHES FROM AUG 28 LOGS
H_GEN    = "7662bf96848c0cd1e03cafc5a6b61785481a55a1c92faec3a248da9195bf9d25"
H_POLL   = "2526f64c73c59fcfeff938b0f4a8b3b610f2294bc6eb6b6b281aa671ac81a08e"
H_LIST   = "9b2cf8d56a4a7edd3db0e40c753cf35314edec9d335ed4f596592080e621758a"
H_SEARCH = "b7a2d663bc0381dd6eb26f8c68f702cb928bea720982f6f5553ea1629a8e871d"
H_META   = "cd94c1ebc6c2ee3bb3c10e1cb7c80cbd05c4470094b10e48a539aaaf36879696"

H_CRE    = "9356b42a4ff6e987347a1f1ee3de7aba4bd103b1cdbfbbc4c5c5fcf52767ad66"
H_UPLOAD = "dd71971acde11807d01862ff1a94657479f7e833af75eac850aa2de0a14fa1fa"
H_ROLL   = "f0778d88963cc4e40749a8ecd9d510808b4a14cd63fac498e7763e6d5d780e5e"
H_18PLUS = "fb22173aa2a43ff08be4221a17094a1445cb212e1b1970a1cee8c37e98d38304"

def get_h(t): 
    return {"Authorization": f"Bearer {t.strip()}", "Content-Type": "application/json", "x-browser-id": "56e77fe10bfcfb337ef2d43bc0df330f", "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Mobile Safari/537.36", "Accept": "application/graphql-response+json,application/json;q=0.9"}

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
    num = int(num)
    if num >= 1000000: return f"{num/1000000:.2f}m"
    if num >= 1000: return f"{num/1000:.2f}k"
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
def search():
    d = request.json
    stype = d.get("type", "ANY_LORA")
    v = {"first": 36, "types": [stype], "feed": d.get("feed", "meilisearch"), "keyword": d.get("keyword", ""), "after": d.get("cursor")}
    if stype == "ANY_LORA": v["loraBaseModelTypes"] = ["SDXL_MODEL"]
    
    params = {"operationName": "listGenerationModels","variables": json.dumps(v),"extensions": json.dumps({"clientLibrary": {"name": "@apollo/client", "version": "4.1.4"}, "persistedQuery": {"version": 1, "sha256Hash": H_SEARCH}})}
    r = requests.get(API_URL, params=params, headers=get_h(d.get("token")))
    res = r.json()
    items = []
    edges = res.get('data', {}).get('generationModels', {}).get('edges', [])
    for e in edges:
        n = e['node']
        thumb = next((u['url'] for u in n['media']['urls'] if u['variant'] == "STILL_THUMBNAIL"), n['media']['urls'][0]['url']) if n.get('media') else ""
        items.append({"name": n['title'], "id": n['id'], "thumb": thumb, "usage": fmt_num(n.get('refCount')), "likes": fmt_num(n.get('likedCount')), "type": n.get('type')})
    page = res.get('data', {}).get('generationModels', {}).get('pageInfo', {})
    return jsonify({"results": items, "cursor": page.get('endCursor') if page.get('hasNextPage') else None, "refreshed_token": check_refresh(r)})

@app.route('/api/lora_meta', methods=['POST'])
def lora_meta():
    d = request.json
    params = {"operationName": "getGenerationModel","variables": json.dumps({"id": d.get("id")}),"extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_META}})}
    r = requests.get(API_URL, params=params, headers=get_h(d.get("token")))
    res = r.json()
    if 'errors' in res or not res.get('data'): return jsonify({"status": "error", "raw": res})
    data = res['data']['generationModel']
    v = data['latestAvailableVersion']
    return jsonify({"v_id": v['id'], "trigger": v['extra'].get('triggerWords', ""), "name": data['title'], "id": d.get("id"), "refreshed_token": check_refresh(r)})

# ================= GENERATION LOGIC =================
@app.route('/api/generate', methods=['POST'])
def generate():
    d = request.json
    lora_configs = d.get("lora_configs", [])
    l_w, l_p, all_t = {}, [], ""
    for conf in lora_configs:
        vid, wgt, trg = conf['v_id'], float(conf['weight']), conf['triggers']
        l_w[vid] = wgt; all_t += f"{trg}, "; l_p.append({"versionId": vid, "weight": wgt, "triggerWords": trg, "positionInfo": {"startIndex": 0, "endIndex": 0}})
    
    payload = {
        "operationName": "createGenerationTask", 
        "variables": {
            "parameters": {
                "prompts": d.get("prompt") + ", " + all_t, 
                "negativePrompts": d.get("neg", ""), 
                "modelId": d.get("modelId"), 
                "width": int(d.get("w", 832)), "height": int(d.get("h", 1248)), 
                "batchSize": int(d.get("batch", 1)), 
                "seed": "", "priority": 1000, 
                "lora": l_w, "loraParameters": l_p, 
                "mediaId": d.get("mediaId"), "strength": float(d.get("strength", 0.55)), 
                "samplingSteps": int(d.get("steps", 28)), "samplingMethod": "Euler a", "cfgScale": float(d.get("cfg", 12.7)), 
                "promptHelper": {"withStage": True, "userWantToEnable": True, "enable": True}
            }, 
            "extra": {"naturalPrompts": str(d.get("prompt"))}
        }, 
        "extensions": {"clientLibrary": {"name": "@apollo/client", "version": "4.1.4"}, "persistedQuery": {"version": 1, "sha256Hash": H_GEN}}
    }
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
    imgs = [i['url'] for i in sr['data']['task']['media']['urls'] if i['variant'] == "PUBLIC"] if status == "completed" else []
    return jsonify({"status": status, "raw": sr, "images": imgs, "refreshed_token": check_refresh(r)})

# ================= DETAILED HISTORY LOGIC (MAPPED TO his.txt) =================
@app.route('/api/tasks', methods=['POST'])
def tasks():
    d = request.json
    vars = {"last": 30, "before": d.get("cursor")}
    # listMyTasksTyped is more efficient for historical lookup
    p = {"operationName": "listMyTasksTyped", "variables": json.dumps(vars), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_LIST}})}
    r = requests.get(API_URL, params=p, headers=get_h(d.get("token")))
    resp_json = r.json()
    task_data = []
    edges = resp_json.get('data', {}).get('me', {}).get('tasks', {}).get('edges', [])
    for edge in reversed(edges):
        node = edge['node']
        if node.get('status') == "completed":
            # Extract parameters correctly from typedParameters or nested parameters
            p_node = node.get('parameters', {})
            extra = p_node.get('extra', {})
            
            # 1. User's Natural Prompt
            nat = extra.get('naturalPrompts', "N/A")
            if isinstance(nat, list) and len(nat) > 0: nat = nat[0]
            
            # 2. Final PixAI Prompt
            final_p = p_node.get('prompts', "N/A")
            
            # 3. LoRAs and Weights
            lora_list = [{"t": l.get('triggerWords'), "w": l.get('weight')} for l in p_node.get('loraParameters', [])]
            
            task_data.append({
                "url": node['media']['urls'][0]['url'] if node.get('media') else "", 
                "p_orig": clean_txt(nat), 
                "p_final": clean_txt(final_p), 
                "neg": clean_txt(p_node.get('negativePrompts', "")), 
                "id": node['id'], 
                "time": format_pixai_time(node.get('createdAt')), 
                "size": f"{p_node.get('width',0)}x{p_node.get('height',0)}", 
                "steps": p_node.get('samplingSteps', 0), 
                "cfg": p_node.get('cfgScale', 0), 
                "ref_url": f"https://api.pixai.art/v1/media/{p_node.get('mediaId')}/thumbnail" if p_node.get('mediaId') else None, 
                "loras": lora_list
            })
    return jsonify({"status": "success", "tasks": task_data, "cursor": resp_json['data']['me']['tasks']['pageInfo']['startCursor'], "refreshed_token": check_refresh(r)})

# ================= RESTORED TOOLS =================
@app.route('/api/daily_claim', methods=['POST'])
def daily_claim():
    r = requests.post(DAILY_URL, headers=get_h(request.json.get("token")), data="")
    return jsonify({"status": "success", "raw": r.text})

@app.route('/api/credits', methods=['POST'])
def credits():
    p = {"operationName":"getMyQuota","variables":"{}","extensions":json.dumps({"persistedQuery":{"version":1,"sha256Hash":H_CRE}})}
    r = requests.get(API_URL, params=p, headers=get_h(request.json.get("token")))
    return jsonify({"credits": r.json()['data']['me']['quotaAmount']})

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
