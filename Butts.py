import requests, json, os
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

API_URL = "https://api.pixai.art/graphql"
# NEW HASH FROM YOUR listm.txt
H_SEARCH = "b7a2d663bc0381dd6eb26f8c68f702cb928bea720982f6f5553ea1629a8e871d"

def get_h(t):
    return {
        "Authorization": f"Bearer {t.strip()}",
        "x-browser-id": "56e77fe10bfcfb337ef2d43bc0df330f",
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Mobile Safari/537.36",
        "Accept": "application/json"
    }

@app.route('/api/search', methods=['POST'])
def search():
    d = request.json
    token = d.get("token")
    
    # Building variables exactly like listm.txt
    variables = {
        "first": 36,
        "types": [d.get("type", "ANY_LORA")], # ANY_LORA or ANY_MODEL
        "feed": d.get("feed", "meilisearch"), # trending, meilisearch, or top_liked
        "keyword": d.get("keyword", "")
    }
    
    # Only add SDXL filter if searching for LoRAs
    if variables["types"] == ["ANY_LORA"]:
        variables["loraBaseModelTypes"] = ["SDXL_MODEL"]
        
    if d.get("cursor"):
        variables["after"] = d.get("cursor")

    # The official site uses GET for search now
    params = {
        "operationName": "listGenerationModels",
        "variables": json.dumps(variables),
        "extensions": json.dumps({
            "persistedQuery": {
                "version": 1,
                "sha256Hash": H_SEARCH
            }
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
            # Find the best thumbnail
            thumb = ""
            if node.get('media') and node['media'].get('urls'):
                # Try to get STILL_THUMBNAIL first, fallback to PUBLIC
                urls = node['media']['urls']
                thumb = next((u['url'] for u in urls if u['variant'] == "STILL_THUMBNAIL"), urls[0]['url'])
            
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
        return jsonify({"error": str(e), "raw": res if 'res' in locals() else None})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
