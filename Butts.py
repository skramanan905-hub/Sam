import requests, json, os
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

API_URL = "https://api.pixai.art/graphql"
# NEW HASH FROM AUGUST 27 LOGS (listm.txt)
H_SEARCH = "b7a2d663bc0381dd6eb26f8c68f702cb928bea720982f6f5553ea1629a8e871d"

def get_h(t):
    return {
        "Authorization": f"Bearer {t.strip()}",
        "x-browser-id": "56e77fe10bfcfb337ef2d43bc0df330f",
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Mobile Safari/537.36",
        "Accept": "application/json"
    }

# THIS FIXES THE "ACTIVE" VIEW ON YOUR URL
@app.route('/')
def index():
    return "Backend Status: Active"

@app.route('/api/search', methods=['POST'])
def search():
    d = request.json
    token = d.get("token")
    
    # Variables mapped exactly from listm.txt
    variables = {
        "first": 36,
        "types": [d.get("type", "ANY_LORA")],
        "feed": d.get("feed", "meilisearch"),
        "keyword": d.get("keyword", "")
    }
    
    # Filter for SDXL if searching LoRAs
    if variables["types"] == ["ANY_LORA"]:
        variables["loraBaseModelTypes"] = ["SDXL_MODEL"]
        
    if d.get("cursor"):
        variables["after"] = d.get("cursor")

    # Official PixAI site uses GET for searches now
    params = {
        "operationName": "listGenerationModels",
        "variables": json.dumps(variables),
        "extensions": json.dumps({
            "persistedQuery": {"version": 1, "sha256Hash": H_SEARCH}
        })
    }

    try:
        r = requests.get(API_URL, params=params, headers=get_h(token))
        res = r.json()
        
        data = res.get('data', {}).get('generationModels', {})
        edges = data.get('edges', [])
        page_info = data.get('pageInfo', {})
        
        results = []
        for e in edges:
            node = e['node']
            urls = node.get('media', {}).get('urls', [])
            # Try to get STILL_THUMBNAIL, otherwise take first URL
            thumb = next((u['url'] for u in urls if u['variant'] == "STILL_THUMBNAIL"), 
                         (urls[0]['url'] if urls else ""))
            
            results.append({
                "id": node['id'],
                "title": node['title'],
                "thumb": thumb,
                "usage": node.get('refCount', 0),
                "likes": node.get('likedCount', 0)
            })
            
        return jsonify({
            "results": results,
            "cursor": page_info.get('endCursor'),
            "hasNext": page_info.get('hasNextPage', False)
        })
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
