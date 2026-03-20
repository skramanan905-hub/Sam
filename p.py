import requests, time, json, re, os
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app) # <--- IMPORTANT: This allows your PHP site to talk to Render

# ================= CONFIGURATION =================
API_URL = "https://api.pixai.art/graphql"
H_GEN    = "61b5dafa7ade64f847051cdca7024b359bae652421834b8f78423d7640f17d96"
H_POLL   = "a32947c6b546befddacd08a3af63cc4ee2277af27fd43342a01fc0414fca3e8a"
H_LORA   = "4e1614f7373d676cb8ec17975796188369ce321a6e78336558ec50f0c2317840"
H_CRE    = "9356b42a4ff6e987347a1f1ee3de7aba4bd103b1cdbfbbc4c5c5fcf52767ad66"
H_SEARCH = "4d76952c681f7d0787077ddeec310f6475ab059e50546248120617abfb4031e9"

def get_h(t):
    return {
        "Authorization": f"Bearer {t.strip()}",
        "Content-Type": "application/json",
        "x-browser-id": "cb8f9647d95c6f5309648829957c0a3d",
        "User-Agent": "Mozilla/5.0"
    }

# --- FEATURE 1: CHECK CREDITS ---
@app.route('/api/credits', methods=['POST'])
def check_credits():
    data = request.json
    token = data.get("token")
    p = {"operationName": "getMyQuota", "variables": "{}", "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_CRE}})}
    try:
        r = requests.get(API_URL, params=p, headers=get_h(token), timeout=10).json()
        return jsonify({"status": "success", "credits": r['data']['me']['quotaAmount']})
    except:
        return jsonify({"status": "error", "message": "API Busy"})

# --- FEATURE 2: SEARCH LORAs ---
@app.route('/api/search', methods=['POST'])
def search_lora():
    data = request.json
    token = data.get("token")
    keyword = data.get("keyword")
    
    vars = {"keyword": keyword, "feed": "meilisearch", "types": ["ANY_LORA"], "first": 20}
    p = {"operationName": "listGenerationModels", "variables": json.dumps(vars), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_SEARCH}})}
    try:
        res = requests.get(API_URL, params=p, headers=get_h(token), timeout=20).json()
        results = []
        for edge in res['data']['generationModels']['edges']:
            n = edge['node']
            thumb = next((u['url'] for u in n['media']['urls'] if u['variant'] == "STILL_THUMBNAIL"), "")
            results.append({"name": n['title'], "id": n['id'], "thumb": thumb})
        return jsonify({"status": "success", "results": results})
    except:
        return jsonify({"status": "error", "message": "Search failed"})

# --- FEATURE 3: GENERATE IMAGE ---
@app.route('/api/generate', methods=['POST'])
def generate():
    data = request.json
    token = data.get("token")
    prompt = data.get("prompt")
    batch = int(data.get("batch", 1))
    
    payload = {
        "operationName": "createGenerationTask",
        "variables": {"parameters": {"prompts": prompt, "modelId": "1861558740588989558", "width": 512, "height": 1024, "batchSize": batch, "samplingSteps": 20, "cfgScale": 7}},
        "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_GEN}}
    }
    
    try:
        res = requests.post(API_URL, json=payload, headers=get_h(token)).json()
        tid = res['data']['createGenerationTask']['id']
        
        # Polling for 3 minutes
        for _ in range(15):
            time.sleep(12)
            status_req = requests.get(API_URL, params={"operationName":"getTaskById","variables":json.dumps({"id":tid}),"extensions":json.dumps({"persistedQuery":{"version":1,"sha256Hash":H_POLL}})}, headers=get_h(token)).json()
            task = status_req['data']['task']
            if task['status'] == "completed":
                urls = [img['url'] for img in task['media']['urls'] if img['variant'] == "PUBLIC"]
                return jsonify({"status": "success", "images": urls})
            if task['status'] == "failed":
                return jsonify({"status": "error", "message": "PixAI Task Failed"})
        return jsonify({"status": "error", "message": "Timeout"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
