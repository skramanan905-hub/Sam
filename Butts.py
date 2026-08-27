import requests, json, re, os, time
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ================= FIXED CONFIG (AUG 27 DATA) =================
API_URL = "https://api.pixai.art/graphql"
H_GEN    = "7662bf96848c0cd1e03cafc5a6b61785481a55a1c92faec3a248da9195bf9d25"
H_POLL   = "2526f64c73c59fcfeff938b0f4a8b3b610f2294bc6eb6b6b281aa671ac81a08e"
H_LIST   = "9b2cf8d56a4a7edd3db0e40c753cf35314edec9d335ed4f596592080e621758a"
H_SEARCH = "b7a2d663bc0381dd6eb26f8c68f702cb928bea720982f6f5553ea1629a8e871d"
H_META   = "cd94c1ebc6c2ee3bb3c10e1cb7c80cbd05c4470094b10e48a539aaaf36879696"

def get_h(t):
    return {
        "Authorization": f"Bearer {t.strip()}",
        "Content-Type": "application/json",
        "x-browser-id": "56e77fe10bfcfb337ef2d43bc0df330f",
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Mobile Safari/537.36"
    }

@app.route('/api/search_models', methods=['POST'])
def search():
    d = request.json
    stype = "ANY_LORA" if d.get('stype') == 'lora' else "ANY_MODEL"
    # Feed options: meilisearch (most used), trending, top_liked
    v = {"keyword": d.get("keyword"), "feed": d.get("feed", "meilisearch"), "types": [stype], "loraBaseModelTypes": ["SDXL_MODEL"], "first": 36, "after": d.get("cursor")}
    params = {"operationName": "listGenerationModels", "variables": json.dumps(v), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_SEARCH}})}
    
    r = requests.get(API_URL, params=params, headers=get_h(d.get("token")))
    res = r.json()
    items = []
    for e in res['data']['generationModels']['edges']:
        n = e['node']
        # CRITICAL: We need the VERSION ID for generation, but the Model ID for Metadata
        v_id = n['latestAvailableVersion']['id'] if n.get('latestAvailableVersion') else n['id']
        items.append({
            "name": n['title'], 
            "model_id": n['id'], # For metadata
            "version_id": v_id,  # For generation
            "thumb": next((u['url'] for u in n['media']['urls'] if u['variant'] == "STILL_THUMBNAIL"), n['media']['urls'][0]['url']),
            "usage": n.get('refCount', 0),
            "likes": n.get('likedCount', 0)
        })
    return jsonify({"results": items, "cursor": res['data']['generationModels']['pageInfo']['endCursor'] if res['data']['generationModels']['pageInfo']['hasNextPage'] else None})

@app.route('/api/lora_meta', methods=['POST'])
def lora_meta():
    d = request.json
    params = {"operationName": "getGenerationModel", "variables": json.dumps({"id": d.get("id")}), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_META}})}
    r = requests.get(API_URL, params=params, headers=get_h(d.get("token")))
    res = r.json()
    data = res['data']['generationModel']
    v = data['latestAvailableVersion']
    return jsonify({"v_id": v['id'], "trigger": v['extra'].get('triggerWords', ""), "name": data['title']})

@app.route('/api/generate', methods=['POST'])
def generate():
    d = request.json
    l_w, l_p, all_t = {}, [], ""
    for conf in d.get("lora_configs", []):
        vid, wgt, trg = conf['v_id'], float(conf['weight']), conf['triggers']
        l_w[vid] = wgt
        all_t += f"{trg}, "
        l_p.append({"versionId": vid, "weight": wgt, "triggerWords": trg, "positionInfo": {"startIndex": 0, "endIndex": 0}})
    
    payload = {
        "operationName": "createGenerationTask",
        "variables": {
            "parameters": {
                "prompts": d.get("prompt") + ", " + all_t,
                "negativePrompts": d.get("neg", "nsfw, low quality"),
                "modelId": d.get("modelId"),
                "width": int(d.get("w", 832)), "height": int(d.get("h", 1248)),
                "batchSize": int(d.get("batch", 4)), "seed": "", "priority": 1000,
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
def check():
    d = request.json
    params = {"operationName": "getTaskById", "variables": json.dumps({"id": d.get("tid")}), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_POLL}})}
    r = requests.get(API_URL, params=params, headers=get_h(d.get("token")))
    res = r.json()
    task = res['data']['task']
    imgs = []
    if task['status'] == "completed":
        # Get the main media or the batch outputs
        if 'outputs' in task and 'batch' in task['outputs']:
            # This is how PixAI stores the 4 images
            imgs = [f"https://images-ng.pixai.art/gi/orig/{t['mediaId']}" for t in task['outputs']['batch']]
        elif task.get('media'):
            imgs = [task['media']['urls'][0]['url']]
    return jsonify({"status": task['status'], "images": imgs})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)
