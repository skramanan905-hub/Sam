import requests, json, time, re, os
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- HASH DATABASE ---
H_GEN, H_POLL, H_LORA, H_SEARCH, H_UPLOAD, H_CRE, H_ROLL, H_REW, H_LIST = (
    "61b5dafa7ade64f847051cdca7024b359bae652421834b8f78423d7640f17d96",
    "a32947c6b546befddacd08a3af63cc4ee2277af27fd43342a01fc0414fca3e8a",
    "4e1614f7373d676cb8ec17975796188369ce321a6e78336558ec50f0c2317840",
    "4d76952c681f7d0787077ddeec310f6475ab059e50546248120617abfb4031e9",
    "dd71971acde11807d01862ff1a94657479f7e833af75eac850aa2de0a14fa1fa",
    "9356b42a4ff6e987347a1f1ee3de7aba4bd103b1cdbfbbc4c5c5fcf52767ad66",
    "f0778d88963cc4e40749a8ecd9d510808b4a14cd63fac498e7763e6d5d780e5e",
    "923002464a8e816706394061c18316cd2d14f5f025dbd1d08020e44cd8a23546",
    "cc067203ddd0846c19d9e247d837c32da498247ec252fe30828434f2f136f53d"
)

API_URL = "https://api.pixai.art/graphql"

def get_h(t): 
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json", "x-browser-id": "08df9bc9358ad97ebfe0ac86284587e5", "User-Agent": "Mozilla/5.0 (Linux; Android 10)"}

@app.route('/api/balance', methods=['POST'])
def get_balance():
    t = request.json.get('token')
    p = {"operationName":"getMyQuota","variables":"{}","extensions":json.dumps({"persistedQuery":{"version":1,"sha256Hash":H_CRE}})}
    r = requests.get(API_URL, params=p, headers=get_h(t)).json()
    return jsonify({"balance": r['data']['me']['quotaAmount']})

@app.route('/api/search', methods=['POST'])
def search_lora():
    d = request.json
    t, kw, cursor = d['token'], d['keyword'], d.get('cursor')
    vars = {"keyword": kw, "feed": "meilisearch", "types": ["ANY_LORA"], "first": 30, "after": cursor}
    p = {"operationName": "listGenerationModels", "variables": json.dumps(vars), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_SEARCH}})}
    res = requests.get(API_URL, params=p, headers=get_h(t)).json()
    items = []
    for edge in res['data']['generationModels']['edges']:
        n = edge['node']
        thumb = next((u['url'] for u in n['media']['urls'] if u['variant'] == "STILL_THUMBNAIL"), None)
        items.append({"title": n['title'], "id": n['id'], "thumb": thumb})
    return jsonify({"items": items, "endCursor": res['data']['generationModels']['pageInfo']['endCursor'], "hasNext": res['data']['generationModels']['pageInfo']['hasNextPage']})

@app.route('/api/claim', methods=['POST'])
def claim_all():
    t = request.json.get('token')
    h = get_h(t)
    requests.post(API_URL, json={"operationName":"rollAprilFools2026Lottery","variables":{},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_ROLL}}}, headers=h)
    for tier in ["tier_100k", "tier_200k", "tier_300k", "tier_400k", "tier_500k"]:
        requests.post("https://api.pixai.art/v2/event/aprilFoolsEvent2026/tier-rewards/aprilFools2026CreditSpending/claim", json={"rewardTierId":tier}, headers=h)
    return jsonify({"status": "success"})

@app.route('/api/generate', methods=['POST'])
def generate():
    d = request.json
    t, prompt, loras, batch, mid, strength = d['token'], d['prompt'], d['loras'], int(d['batch']), d.get('mid'), float(d.get('str', 0.55))
    
    # Process LoRAs
    w, p, tr = {}, [], ""
    for lid in loras:
        p_l = {"operationName": "getGenerationModel", "variables": json.dumps({"id": lid}), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_LORA}})}
        rl = requests.get(API_URL, params=p_l, headers=get_h(t)).json()
        v = rl['data']['generationModel']['latestAvailableVersion']
        w[v['id']] = 0.7; tr += f", {v['extra'].get('triggerWords', '')}"
        p.append({"versionId": v['id'], "weight": 0.7, "triggerWords": v['extra'].get('triggerWords', ''), "positionInfo": {"startIndex": 0, "endIndex": 0}})
    
    full_p = prompt + tr
    payload = {"operationName": "createGenerationTask", "variables": {"parameters": {"prompts": full_p, "modelId": "1861558740588989558", "width": 512, "height": 1024, "batchSize": batch, "lora": w, "loraParameters": p, "mediaId": mid, "strength": strength, "samplingSteps": 28, "samplingMethod": "Euler a", "cfgScale": 5, "promptHelper": {"withStage": True, "userWantToEnable": True, "enable": True}}}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_GEN}}}
    
    res = requests.post(API_URL, json=payload, headers=get_h(t)).json()
    tid = res['data']['createGenerationTask']['id']
    
    while True:
        time.sleep(15)
        sr = requests.get(API_URL, params={"operationName":"getTaskById","variables":json.dumps({"id":tid}),"extensions":json.dumps({"persistedQuery":{"version":1,"sha256Hash":H_POLL}})}, headers=get_h(t)).json()
        task = sr['data']['task']
        if task['status'] == "completed":
            urls = [u['url'] for u in task['media']['urls'] if u['variant'] == "PUBLIC"]
            return jsonify({"urls": urls, "prompt": full_p})
        if task['status'] == "failed": return jsonify({"error": "failed"})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
