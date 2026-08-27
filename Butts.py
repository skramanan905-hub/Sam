import requests, time, json, re, os
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ================= MASTER CONFIGURATION (UPDATED AUGUST 27, 2026) =================
API_URL = "https://api.pixai.art/graphql"
DAILY_URL = "https://api.pixai.art/v2/claim/pixai-daily-credits"
REST_FOLLOW_URL = "https://api.pixai.art/v2/quest-v2/report-social-follow"
REST_VISIT_URL = "https://api.pixai.art/v2/quest-v2/report-visit"

# UPDATED HASHES FROM AUGUST 27 LOGS
H_GEN    = "7662bf96848c0cd1e03cafc5a6b61785481a55a1c92faec3a248da9195bf9d25" # createGenerationTask
H_POLL   = "2526f64c73c59fcfeff938b0f4a8b3b610f2294bc6eb6b6b281aa671ac81a08e" # getTaskById
H_LIST   = "9b2cf8d56a4a7edd3db0e40c753cf35314edec9d335ed4f596592080e621758a" # listMyTasksTyped
H_SEARCH = "b7a2d663bc0381dd6eb26f8c68f702cb928bea720982f6f5553ea1629a8e871d" # listGenerationModels
H_META   = "cd94c1ebc6c2ee3bb3c10e1cb7c80cbd05c4470094b10e48a539aaaf36879696" # getGenerationModel
H_CRE    = "9356b42a4ff6e987347a1f1ee3de7aba4bd103b1cdbfbbc4c5c5fcf52767ad66" # getMyQuota
H_UPLOAD = "dd71971acde11807d01862ff1a94657479f7e833af75eac850aa2de0a14fa1fa"
H_18PLUS = "fb22173aa2a43ff08be4221a17094a1445cb212e1b1970a1cee8c37e98d38304"

def get_h(t): 
    return {
        "Authorization": f"Bearer {t.strip()}", 
        "Content-Type": "application/json", 
        "x-browser-id": "56e77fe10bfcfb337ef2d43bc0df330f", 
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Mobile Safari/537.36"
    }

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

@app.route('/api/search_models', methods=['POST'])
def search_models():
    d = request.json
    v = {"keyword": d.get("keyword"), "feed": "meilisearch", "types": ["ANY_MODEL"], "first": 36, "after": d.get("cursor")}
    # Updated to GET as per listm.txt
    params = {
        "operationName": "listGenerationModels",
        "variables": json.dumps(v),
        "extensions": json.dumps({"clientLibrary": {"name": "@apollo/client", "version": "4.1.4"}, "persistedQuery": {"version": 1, "sha256Hash": H_SEARCH}})
    }
    r = requests.get(API_URL, params=params, headers=get_h(d.get("token")))
    res = r.json()
    items = []
    for e in res['data']['generationModels']['edges']:
        n = e['node']
        m_id = n['latestAvailableVersion']['id'] if n.get('latestAvailableVersion') else n['id']
        items.append({
            "name": n['title'], 
            "id": m_id, 
            "thumb": next((u['url'] for u in n['media']['urls'] if u['variant'] == "STILL_THUMBNAIL"), ""), 
            "usage": fmt_num(n.get('refCount')), 
            "likes": fmt_num(n.get('likedCount'))
        })
    return jsonify({"results": items, "cursor": res['data']['generationModels']['pageInfo']['endCursor'] if res['data']['generationModels']['pageInfo']['hasNextPage'] else None})

@app.route('/api/search', methods=['POST'])
def search_loras():
    d = request.json
    v = {"keyword": d.get("keyword"), "feed": "meilisearch", "types": ["ANY_LORA"], "loraBaseModelTypes": ["SDXL_MODEL"], "first": 36, "after": d.get("cursor")}
    params = {
        "operationName": "listGenerationModels",
        "variables": json.dumps(v),
        "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_SEARCH}})
    }
    r = requests.get(API_URL, params=params, headers=get_h(d.get("token")))
    res = r.json()
    items = []
    for e in res['data']['generationModels']['edges']:
        n = e['node']
        items.append({ "name": n['title'], "id": n['id'], "thumb": next((u['url'] for u in n['media']['urls'] if u['variant'] == "STILL_THUMBNAIL"), ""), "usage": fmt_num(n.get('refCount')), "likes": fmt_num(n.get('likedCount'))})
    return jsonify({"results": items, "cursor": res['data']['generationModels']['pageInfo']['endCursor'] if res['data']['generationModels']['pageInfo']['hasNextPage'] else None})

@app.route('/api/lora_meta', methods=['POST'])
def lora_meta():
    d = request.json
    # Updated to GET as per model.txt
    params = {
        "operationName": "getGenerationModel",
        "variables": json.dumps({"id": d.get("id")}),
        "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_META}})
    }
    r = requests.get(API_URL, params=params, headers=get_h(d.get("token")))
    res = r.json()
    if not res.get('data') or not res['data'].get('generationModel'): return jsonify({"status": "error", "msg": "Model Not Found"})
    data = res['data']['generationModel']
    v = data['latestAvailableVersion']
    return jsonify({"v_id": v['id'], "trigger": v['extra'].get('triggerWords', ""), "name": data['title'], "id": d.get("id")})

@app.route('/api/generate', methods=['POST'])
def generate():
    d = request.json
    token = d.get("token")
    lora_configs = d.get("lora_configs", [])
    l_w, l_p, all_t = {}, [], ""
    for conf in lora_configs:
        vid, wgt, trg = conf['v_id'], float(conf['weight']), conf['triggers']
        l_w[vid] = wgt; all_t += f"{trg}, "; l_p.append({"versionId": vid, "weight": wgt, "triggerWords": trg, "positionInfo": {"startIndex": 0, "endIndex": 0}})
    
    # PAYLOAD UPDATED TO MATCH creat.txt EXACTLY
    payload = {
        "operationName": "createGenerationTask", 
        "variables": {
            "parameters": {
                "prompts": d.get("prompt") + ", " + all_t, 
                "negativePrompts": d.get("neg", "nsfw, worst quality, bad quality, low quality"), 
                "modelId": d.get("modelId"), 
                "width": int(d.get("w", 768)), 
                "height": int(d.get("h", 1280)), 
                "batchSize": int(d.get("batch", 4)), 
                "seed": "",
                "priority": 1000, 
                "lora": l_w, 
                "loraParameters": l_p, 
                "samplingSteps": int(d.get("steps", 28)), 
                "samplingMethod": "Euler a", 
                "cfgScale": float(d.get("cfg", 5.0)), 
                "controlNets": [],
                "promptHelper": {"withStage": True, "userWantToEnable": True, "forcePromptHelperDetectionSide": "server"}
            }, 
            "extra": {"naturalPrompts": str(d.get("prompt"))}
        }, 
        "extensions": {
            "clientLibrary": {"name": "@apollo/client", "version": "4.1.4"},
            "persistedQuery": {"version": 1, "sha256Hash": H_GEN}
        }
    }
    
    r_init = requests.post(API_URL, json=payload, headers=get_h(token))
    res_raw = r_init.json()
    if 'errors' in res_raw: return jsonify({"status": "error", "raw": res_raw})
    return jsonify({"status": "started", "tid": res_raw['data']['createGenerationTask']['id']})

@app.route('/api/check_task', methods=['POST'])
def check_task():
    d = request.json
    tid, token = d.get("tid"), d.get("token")
    # Updated to GET as per get.txt
    params = {
        "operationName": "getTaskById",
        "variables": json.dumps({"id": tid}),
        "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_POLL}})
    }
    r_poll = requests.get(API_URL, params=params, headers=get_h(token))
    sr = r_poll.json()
    if 'errors' in sr: return jsonify({"status": "error", "raw": sr})
    task = sr['data']['task']
    status = task['status']
    
    images = []
    if status == "completed" and task.get('media'):
        images = [task['media']['urls'][0]['url']] # Primary image
        if 'outputs' in task and 'batch' in task['outputs']:
            # Try to get batch images if available (requires extra lookups usually, but we check here)
            pass
            
    return jsonify({"status": status, "images": images, "refreshed_token": check_refresh(r_poll)})

@app.route('/api/tasks', methods=['POST'])
def tasks():
    d = request.json
    t = d.get("token")
    # Updated to listMyTasksTyped as per listmy.txt
    vars = {"last": 30, "before": d.get("cursor")}
    params = {
        "operationName": "listMyTasksTyped",
        "variables": json.dumps(vars),
        "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_LIST}})
    }
    r = requests.get(API_URL, params=params, headers=get_h(t))
    resp_json = r.json()
    task_data = []
    
    for edge in reversed(resp_json['data']['me']['tasks']['edges']):
        node = edge['node']
        if node['status'] == "completed" and node.get('media'):
            task_data.append({
                "url": node['media']['urls'][0]['url'], 
                "id": node['id'], 
                "time": format_pixai_time(node.get('createdAt'))
            })
            
    return jsonify({
        "status": "success", 
        "tasks": task_data, 
        "cursor": resp_json['data']['me']['tasks']['pageInfo']['startCursor'] if resp_json['data']['me']['tasks']['pageInfo']['hasPreviousPage'] else None
    })

@app.route('/api/credits', methods=['POST'])
def credits():
    params = {"operationName":"getMyQuota","variables":"{}","extensions":json.dumps({"persistedQuery":{"version":1,"sha256Hash":H_CRE}})}
    r = requests.get(API_URL, params=params, headers=get_h(request.json.get("token")))
    return jsonify({"credits": r.json()['data']['me']['quotaAmount']})

@app.route('/api/upload', methods=['POST'])
def upload():
    t, f = request.form.get("token"), request.files['image'].read()
    h = get_h(t)
    # Upload mutation remains POST
    r1 = requests.post(API_URL, json={"operationName":"uploadMedia","variables":{"input":{"type":"IMAGE","provider":"S3"}},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_UPLOAD}}}, headers=h).json()
    requests.put(r1['data']['uploadMedia']['uploadUrl'], data=f)
    ext_id = r1['data']['uploadMedia']['uploadUrl'].split('/')[-1].split('?')[0]
    r3 = requests.post(API_URL, json={"operationName":"uploadMedia","variables":{"input":{"type":"IMAGE","provider":"S3","externalId":ext_id}},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_UPLOAD}}}, headers=h).json()
    return jsonify({"success": True, "mediaId": r3['data']['uploadMedia']['mediaId']})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
