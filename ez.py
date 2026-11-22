import os
import time
import json
import uuid
import base64
from curl_cffi import requests as curl_requests
from flask import Flask, request, jsonify, Response
from flask_cors import CORS

app = Flask(__name__)
# Enable CORS for all routes and origins
CORS(app, resources={r"/*": {"origins": "*"}})

BASE_URL = "https://magichour.ai"

def get_fresh_session():
    session = curl_requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Linux; Android 15; I2301 Build/AP3A.240905.015.A2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.8103.50 Mobile Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/products/ai-video-generator",
        "x-requested-with": "mark.via.gp",
        "x-timezone-offset": "-330",
        "sec-ch-ua": '"Not-A.Brand";v="99", "Android WebView";v="157", "Chromium";v="157"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty"
    })

    # Fake Device ID to reset the limit
    fake_distinct_id = str(uuid.uuid4())
    fake_created_at = int(time.time() * 1000)
    fake_mh_did = base64.b64encode(json.dumps({
        "distinct_id": fake_distinct_id,
        "created_at": fake_created_at
    }).encode()).decode()
    session.cookies.set("mh_did", fake_mh_did)
    
    session.get(f"{BASE_URL}/api/auth/csrf", impersonate="chrome")
    return session

@app.route('/')
def home():
    # This allows Render to see the port is open and active
    return "Magic Hour Backend is Running!"

@app.route('/api/generate', methods=['POST', 'OPTIONS'])
def generate():
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        return '', 200

    prompt = request.form.get('prompt', '')
    image_file = request.files.get('image')

    if not prompt or not image_file:
        return jsonify({"status": "error", "message": "Prompt and image are required"}), 400

    image_bytes = image_file.read()
    content_type = image_file.content_type or "image/jpeg"

    def generate_stream():
        try:
            yield "data: " + json.dumps({"log": "🔄 Creating new session..."}) + "\n\n"
            session = get_fresh_session()
            
            # Generate ONE task ID and use it everywhere
            task_id = str(uuid.uuid4())
            
            # --- Step 1: Get Upload URL ---
            yield "data: " + json.dumps({"log": "☁️ Requesting upload slot..."}) + "\n\n"
            upload_req_payload = {
                "json": {
                    "assetPrefix": "image-to-video",
                    "taskId": task_id,
                    "fileName": "source.jpg",
                    "fileType": content_type,
                    "filePrefix": "source",
                    "includeReadUrl": False
                }
            }
            r = session.post(f"{BASE_URL}/rpc/freeToolUpload/getResumableUploadUrl", json=upload_req_payload, impersonate="chrome")
            
            if r.status_code != 200:
                yield "data: " + json.dumps({"error": f"Upload URL failed: {r.text[:100]}"}) + "\n\n"
                return
            
            upload_data = r.json().get("json", {})
            upload_url = upload_data.get("uploadUrl")
            file_path = upload_data.get("filePath")
            
            if not upload_url or not file_path:
                yield "data: " + json.dumps({"error": "No upload URL returned from Magic Hour."}) + "\n\n"
                return
            
            # --- Step 2: Upload Image ---
            yield "data: " + json.dumps({"log": "📤 Uploading image..."}) + "\n\n"
            file_size = len(image_bytes)
            headers = {
                "Content-Type": content_type,
                "Content-Length": str(file_size),
                "Content-Range": f"bytes 0-{file_size-1}/{file_size}"
            }
            put_res = session.put(upload_url, data=image_bytes, headers=headers, impersonate="chrome")
            
            if put_res.status_code not in [200, 201]:
                yield "data: " + json.dumps({"error": f"Upload failed: {put_res.status_code}"}) + "\n\n"
                return

            # --- Step 3: Start Generation ---
            yield "data: " + json.dumps({"log": "🎟️ Starting generation..."}) + "\n\n"
            payload = {
                "prompt": prompt,
                "image_file_path": file_path, 
                "aspect_ratio": "9:16",
                "model": "any-to-video-v5",
                "duration": 5,
                "client_request_id": task_id # SAME TASK ID
            }
            r = session.post(f"{BASE_URL}/api/free-tools/v5/any-to-video", json=payload, impersonate="chrome")
            
            if r.status_code == 429:
                yield "data: " + json.dumps({"error": "Limit Reached! Render IP is blocked."}) + "\n\n"
                return
            elif r.status_code != 200:
                yield "data: " + json.dumps({"error": f"Generation failed: {r.text[:100]}"}) + "\n\n"
                return

            # --- Step 4: Poll for Result ---
            start_time = time.time()
            while True:
                # SAME TASK ID
                r = session.get(f"{BASE_URL}/api/free-tools/v5/any-to-video/{task_id}/status", impersonate="chrome")
                job_data = r.json()
                status = job_data.get("status")
                position = job_data.get("position", "?")
                
                elapsed = int(time.time() - start_time)
                mins, secs = divmod(elapsed, 60)
                timer_str = f"{mins}m {secs}s"
                
                if status == "SUCCESS":
                    video_url = job_data["files"][0]["url"]
                    yield "data: " + json.dumps({"success": video_url}) + "\n\n"
                    return
                elif status == "FAILED":
                    yield "data: " + json.dumps({"error": "Rendering failed on Magic Hour."}) + "\n\n"
                    return
                    
                yield "data: " + json.dumps({"log": f"⏳ Rendering... ({timer_str}) | Queue: {position}"}) + "\n\n"
                time.sleep(4)

        except Exception as e:
            yield "data: " + json.dumps({"error": str(e)}) + "\n\n"

    return Response(generate_stream(), mimetype="text/event-stream")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
