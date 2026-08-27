import requests, json, os
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
# Crucial: Allow InfinityFree to talk to Render
CORS(app)

API_URL = "https://api.pixai.art/graphql"
# NEW HASH FROM YOUR listm.txt (Aug 27)
H_SEARCH = "b7a2d663bc0381dd6eb26f8c68f702cb928bea720982f6f5553ea1629a8e871d"

def get_h(t):
    return {
        "Authorization": f"Bearer {t.strip()}",
        "x-browser-id": "56e77fe10bfcfb337ef2d43bc0df330f", # From your log
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Mobile Safari/537.36",
        "Content-Type": "application/json",
        "Accept": "application/graphql-response+json,application/json;q=0.9"
    }

@app.route('/')
def index():
    # This makes your Render URL show "Active"
    return "<h1>PixAI Backend: Active</h1>"

@app.route('/api/search', methods=['POST'])
def search():
    try:
        d = request.json
        token = d.get("token")
        kw = d.get("keyword", "")
        cursor = d.get("cursor")
        stype = d.get("type", "ANY_LORA") # ANY_LORA or ANY_MODEL
        
        # Variables structure must match listm.txt EXACTLY
        variables = {
            "first": 36,
            "types": [stype],
            "feed": d.get("feed", "meilisearch"), # trending, meilisearch, or top_liked
            "keyword": kw
        }
        
        if stype == "ANY_LORA":
            variables["loraBaseModelTypes"] = ["SDXL_MODEL"]
            
        if cursor:
            variables["after"] = cursor

        # The August 27 log shows PixAI uses GET for listGenerationModels
        extensions = {
            "clientLibrary": {"name": "@apollo/client", "version": "4.1.4"},
            "persistedQuery": {"version": 1, "sha256Hash": H_SEARCH}
        }

        params = {
            "operationName": "listGenerationModels",
            "variables": json.dumps(variables),
            "extensions": json.dumps(extensions)
        }

        r = requests.get(API_URL, params=params, headers=get_h(token), timeout=15)
        
        # Check if request was successful
        if r.status_code != 200:
            return jsonify({"status": "error", "msg": f"PixAI Error {r.status_code}"}), 400

        res = r.json()
        
        # Safe extraction of data
        data_root = res.get('data', {}).get('generationModels', {})
        edges = data_root.get('edges', [])
        page_info = data_root.get('pageInfo', {})
        
        results = []
        for e in edges:
            n = e['node']
            # Find the correct thumbnail variant
            thumb = ""
            if n.get('media') and n['media'].get('urls'):
                thumb = next((u['url'] for u in n['media']['urls'] if u['variant'] == "STILL_THUMBNAIL"), n['media']['urls'][0]['url'])
            
            results.append({
                "id": n['id'],
                "title": n['title'],
                "thumb": thumb,
                "usage": n.get('refCount', 0),
                "likes": n.get('likedCount', 0),
                "type": n.get('type')
            })
            
        return jsonify({
            "status": "success",
            "results": results,
            "cursor": page_info.get('endCursor'),
            "hasNext": page_info.get('hasNextPage', False)
        })

    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)}), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
