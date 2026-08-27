import requests, time, json, re, os
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ================= MASTER CONFIGURATION (AUG 27 UPDATE) =================
API_URL = "https://api.pixai.art/graphql"

# Hashes from your listm.txt, creat.txt, and get.txt
H_GEN    = "7662bf96848c0cd1e03cafc5a6b61785481a55a1c92faec3a248da9195bf9d25" 
H_POLL   = "2526f64c73c59fcfeff938b0f4a8b3b610f2294bc6eb6b6b281aa671ac81a08e"
H_LIST   = "9b2cf8d56a4a7edd3db0e40c753cf35314edec9d335ed4f596592080e621758a"
H_SEARCH = "b7a2d663bc0381dd6eb26f8c68f702cb928bea720982f6f5553ea1629a8e871d" # From listm.txt
H_META   = "cd94c1ebc6c2ee3bb3c10e1cb7c80cbd05c4470094b10e48a539aaaf36879696"
H_CRE    = "9356b42a4ff6e987347a1f1ee3de7aba4bd103b1cdbfbbc4c5c5fcf52767ad66"
H_UPLOAD = "dd71971acde11807d01862ff1a94657479f7e833af75eac850aa2de0a14fa1fa"

def get_h(t): 
    return {
        "Authorization": f"Bearer {t.strip()}",
        "x-browser-id": "56e77fe10bfcfb337ef2d43bc0df330f",
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Mobile Safari/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

def fmt_num(num):
    if not num: return "0"
    num = int(num)
    if num >= 1000: return f"{num/1000:.1f}k"
    return str(num)

@app.route('/api/search', methods=['POST'])
def search():
    d = request.json
    # PixAI Search uses GET with params now
    variables = {
        "first": 36,
        "types": ["ANY_LORA"] if d.get('stype') == 'lora' else ["ANY_MODEL"],
        "feed": d.get('feed', 'meilisearch'),
        "keyword": d.get('keyword')
    }
    if d.get('cursor'): variables["after"] = d.get('cursor')
    if d.get('stype') == 'lora': variables["loraBaseModelTypes"] = ["SDXL_MODEL"]

    params = {
        "operationName": "listGenerationModels",
        "variables": json.dumps(variables),
        "extensions": json.dumps({
            "clientLibrary": {"name": "@apollo/client", "version": "4.1.4"},
            "persistedQuery": {"version": 1, "sha256Hash": H_SEARCH}
        })
    }

    r = requests.get(API_URL, params=params, headers=get_h(d.get("token")))
    res = r.json()
    
    items = []
    if 'data' in res and res['data']['generationModels']:
        for e in res['data']['generationModels']['edges']:
            n = e['node']
            # Match the UI: title, usage (refCount), likes
            thumb = next((u['url'] for u in n['media']['urls'] if u['variant'] == "STILL_THUMBNAIL"), n['media']['urls'][0]['url'] if n.get('media') else "")
            items.append({
                "name": n['title'],
                "id": n['id'],
                "thumb": thumb,
                "usage": fmt_num(n.get('refCount')),
                "likes": fmt_num(n.get('likedCount'))
            })
    
    return jsonify({
        "results": items, 
        "cursor": res['data']['generationModels']['pageInfo']['endCursor'] if res['data']['generationModels']['pageInfo']['hasNextPage'] else None
    })

@app.route('/api/generate', methods=['POST'])
def generate():
    d = request.json
    token = d.get("token")
    lora_configs = d.get("lora_configs", [])
    l_w, l_p = {}, []
    for conf in lora_configs:
        vid, wgt, trg = conf['v_id'], float(conf['weight']), conf['triggers']
        l_w[vid] = wgt
        l_p.append({"versionId": vid, "weight": wgt, "triggerWords": trg, "positionInfo": {"startIndex": 0, "endIndex": 0}})
    
    payload = {
        "operationName": "createGenerationTask", 
        "variables": {
            "parameters": {
                "prompts": d.get("prompt"), 
                "negativePrompts": d.get("neg", ""), 
                "modelId": d.get("modelId"), 
                "width": int(d.get("w", 832)), 
                "height": int(d.get("h", 1248)), 
                "batchSize": int(d.get("batch", 4)), 
                "seed": "",
                "priority": 1000, 
                "lora": l_w, 
                "loraParameters": l_p, 
                "mediaId": d.get("mediaId"), 
                "strength": float(d.get("strength", 0.55)), 
                "samplingSteps": int(d.get("steps", 28)), 
                "samplingMethod": "Euler a", 
                "cfgScale": float(d.get("cfg", 5.0)), 
                "promptHelper": {"withStage": True, "userWantToEnable": True, "forcePromptHelperDetectionSide": "server"}
            }, 
            "extra": {"naturalPrompts": str(d.get("prompt"))}
        }, 
        "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_GEN}}
    }
    
    r_init = requests.post(API_URL, json=payload, headers=get_h(token))
    res_raw = r_init.json()
    if 'errors' in res_raw: return jsonify({"status": "error", "raw": res_raw})
    return jsonify({"status": "started", "tid": res_raw['data']['createGenerationTask']['id']})

@app.route('/api/check_task', methods=['POST'])
def check_task():
    d = request.json
    params = {
        "operationName": "getTaskById",
        "variables": json.dumps({"id": d.get("tid")}),
        "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_POLL}})
    }
    r = requests.get(API_URL, params=params, headers=get_h(d.get("token")))
    sr = r.json()
    task = sr['data']['task']
    images = []
    if task['status'] == "completed" and task.get('media'):
        # Get the main image
        images.append(task['media']['urls'][0]['url'])
        # If batch, get others
        if 'outputs' in task and 'batch' in task['outputs']:
             pass # Logic to fetch sub-images if needed
    return jsonify({"status": task['status'], "images": images})

@app.route('/api/lora_meta', methods=['POST'])
def lora_meta():
    d = request.json
    params = {"operationName":"getGenerationModel","variables":json.dumps({"id":d.get("id")}),"extensions":json.dumps({"persistedQuery":{"version":1,"sha256Hash":H_META}})}
    r = requests.get(API_URL, params=params, headers=get_h(d.get("token")))
    res = r.json()
    data = res['data']['generationModel']
    v = data['latestAvailableVersion']
    return jsonify({"v_id": v['id'], "trigger": v['extra'].get('triggerWords', ""), "name": data['title']})

@app.route('/api/credits', methods=['POST'])
def credits():
    params = {"operationName":"getMyQuota","variables":"{}","extensions":json.dumps({"persistedQuery":{"version":1,"sha256Hash":H_CRE}})}
    r = requests.get(API_URL, params=params, headers=get_h(request.json.get("token")))
    return jsonify({"credits": r.json()['data']['me']['quotaAmount']})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
