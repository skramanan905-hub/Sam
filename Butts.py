import requests, json, re, os
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ================= UPDATED MASTER CONFIG (AUG 27, 2026) =================
API_URL = "https://api.pixai.art/graphql"
H_SEARCH = "b7a2d663bc0381dd6eb26f8c68f702cb928bea720982f6f5553ea1629a8e871d"
H_GEN    = "7662bf96848c0cd1e03cafc5a6b61785481a55a1c92faec3a248da9195bf9d25"
H_POLL   = "2526f64c73c59fcfeff938b0f4a8b3b610f2294bc6eb6b6b281aa671ac81a08e"
H_LIST   = "9b2cf8d56a4a7edd3db0e40c753cf35314edec9d335ed4f596592080e621758a"
H_META   = "cd94c1ebc6c2ee3bb3c10e1cb7c80cbd05c4470094b10e48a539aaaf36879696"
H_CRE    = "9356b42a4ff6e987347a1f1ee3de7aba4bd103b1cdbfbbc4c5c5fcf52767ad66"
H_UPLOAD = "dd71971acde11807d01862ff1a94657479f7e833af75eac850aa2de0a14fa1fa"

def get_h(t):
    return {
        "Authorization": f"Bearer {t.strip()}",
        "x-browser-id": "56e77fe10bfcfb337ef2d43bc0df330f",
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Mobile Safari/537.36",
        "Accept": "application/graphql-response+json,application/json"
    }

def fmt_num(num):
    if not num: return "0"
    num = int(num)
    if num >= 1000: return f"{num/1000:.1f}k"
    return str(num)

@app.route('/api/search', methods=['POST'])
def search():
    d = request.json
    # feed: trending, meilisearch (most used), top_liked
    # types: ANY_LORA or ANY_MODEL
    v = {
        "first": 36,
        "types": [d.get("type", "ANY_LORA")],
        "feed": d.get("feed", "trending"),
        "keyword": d.get("keyword", "")
    }
    if d.get("cursor"): v["after"] = d.get("cursor")
    
    # Matching official logs: GET request with stringified params
    params = {
        "operationName": "listGenerationModels",
        "variables": json.dumps(v),
        "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_SEARCH}})
    }
    
    r = requests.get(API_URL, params=params, headers=get_h(d.get("token")))
    res = r.json()
    
    output = []
    try:
        edges = res['data']['generationModels']['edges']
        for e in edges:
            n = e['node']
            thumb = ""
            if n.get('media') and n['media'].get('urls'):
                thumb = next((u['url'] for u in n['media']['urls'] if u['variant'] == "STILL_THUMBNAIL"), "")
            
            output.append({
                "id": n['id'],
                "title": n['title'],
                "thumb": thumb,
                "usage": fmt_num(n.get('refCount')),
                "likes": fmt_num(n.get('likedCount'))
            })
        
        return jsonify({
            "results": output,
            "cursor": res['data']['generationModels']['pageInfo']['endCursor'],
            "hasNext": res['data']['generationModels']['pageInfo']['hasNextPage']
        })
    except Exception as e:
        return jsonify({"error": str(e), "raw": res})

@app.route('/api/lora_meta', methods=['POST'])
def lora_meta():
    d = request.json
    params = {
        "operationName": "getGenerationModel",
        "variables": json.dumps({"id": d.get("id")}),
        "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_META}})
    }
    r = requests.get(API_URL, params=params, headers=get_h(d.get("token")))
    res = r.json()
    try:
        data = res['data']['generationModel']
        v = data['latestAvailableVersion']
        return jsonify({"v_id": v['id'], "trigger": v['extra'].get('triggerWords', ""), "name": data['title']})
    except: return jsonify({"status": "error"})

@app.route('/api/generate', methods=['POST'])
def generate():
    d = request.json
    l_w, l_p, all_t = {}, [], ""
    for conf in d.get("lora_configs", []):
        vid, wgt, trg = conf['v_id'], float(conf['weight']), conf['triggers']
        l_w[vid] = wgt; all_t += f"{trg}, "; l_p.append({"versionId": vid, "weight": wgt, "triggerWords": trg, "positionInfo": {"startIndex": 0, "endIndex": 0}})
    
    payload = {
        "operationName": "createGenerationTask",
        "variables": {
            "parameters": {
                "prompts": d.get("prompt") + ", " + all_t,
                "negativePrompts": d.get("neg", "nsfw, low quality"),
                "modelId": d.get("modelId"),
                "width": int(d.get("w", 832)),
                "height": int(d.get("h", 1248)),
                "batchSize": int(d.get("batch", 4)),
                "seed": "", "priority": 1000,
                "lora": l_w, "loraParameters": l_p,
                "samplingSteps": 28, "samplingMethod": "Euler a", "cfgScale": 5.0,
                "promptHelper": {"withStage": True, "userWantToEnable": True, "forcePromptHelperDetectionSide": "server"}
            },
            "extra": {"naturalPrompts": str(d.get("prompt"))}
        },
        "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_GEN}}
    }
    r = requests.post(API_URL, json=payload, headers=get_h(d.get("token")))
    return r.text

@app.route('/api/check_task', methods=['POST'])
def check_task():
    d = request.json
    params = {"operationName":"getTaskById","variables":json.dumps({"id":d.get("tid")}),"extensions":json.dumps({"persistedQuery":{"version":1,"sha256Hash":H_POLL}})}
    r = requests.get(API_URL, params=params, headers=get_h(d.get("token")))
    return r.text

@app.route('/api/tasks', methods=['POST'])
def tasks():
    d = request.json
    v = {"last": 30}
    if d.get("cursor"): v["before"] = d.get("cursor")
    params = {"operationName":"listMyTasksTyped","variables":json.dumps(v),"extensions":json.dumps({"persistedQuery":{"version":1,"sha256Hash":H_LIST}})}
    r = requests.get(API_URL, params=params, headers=get_h(d.get("token")))
    return r.text

@app.route('/api/credits', methods=['POST'])
def credits():
    p = {"operationName":"getMyQuota","variables":"{}","extensions":json.dumps({"persistedQuery":{"version":1,"sha256Hash":H_CRE}})}
    return requests.get(API_URL, params=p, headers=get_h(request.json.get("token"))).text

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
