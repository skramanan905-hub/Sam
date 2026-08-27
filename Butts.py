import requests, os, json
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

API_URL = "https://api.pixai.art/graphql"
# New Search Hash from your TG Bot
H_MODEL_SEARCH = "b7a2d663bc0381dd6eb26f8c68f702cb928bea720982f6f5553ea1629a8e871d"

def get_headers(token):
    return {
        "Authorization": f"Bearer {token.strip()}",
        "Content-Type": "application/json",
        "x-browser-id": "56e77fe10bfcfb337ef2d43bc0df330f",
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Mobile Safari/537.36"
    }

@app.route('/api/search', methods=['POST'])
def search():
    data = request.json
    token = data.get("token")
    keyword = data.get("keyword")
    feed = data.get("sort", "meilisearch") # Default to Most Used
    cursor = data.get("cursor", None)

    variables = {
        "first": 20,
        "types": ["ANY_LORA"],
        "loraBaseModelTypes": ["SDXL_MODEL"], # Sync with your TG bot logic
        "feed": feed,
        "keyword": keyword
    }
    if cursor:
        variables["after"] = cursor

    payload = {
        "operationName": "listGenerationModels",
        "variables": variables,
        "extensions": {
            "persistedQuery": {"version": 1, "sha256Hash": H_MODEL_SEARCH}
        }
    }

    try:
        r = requests.post(API_URL, json=payload, headers=get_headers(token))
        res = r.json()
        
        edges = res['data']['generationModels']['edges']
        page_info = res['data']['generationModels']['pageInfo']
        
        results = []
        for e in edges:
            n = e['node']
            thumb = ""
            if n.get('media') and n['media'].get('urls'):
                thumb = next((u['url'] for u in n['media']['urls'] if u['variant'] == "STILL_THUMBNAIL"), "")
            
            results.append({
                "id": n['id'],
                "title": n['title'],
                "thumb": thumb,
                "uses": n.get('refCount', 0),
                "likes": n.get('likedCount', 0)
            })

        return jsonify({
            "status": "success",
            "results": results,
            "cursor": page_info['endCursor'] if page_info['hasNextPage'] else None
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
