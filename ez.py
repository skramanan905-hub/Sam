import os
import time
import json
import uuid
import hashlib
import base64
import random
import requests
from flask import Flask, request, jsonify, Response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

BASE_URL = "https://raphael.app"

# ALL ANDROID USER AGENTS (Matching your phone)
USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 15; I2301 Build/AP3A.240905.015.A2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.8103.50 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; moto g stylus) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 11; Redmi Note 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36"
]

def get_fresh_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "*/*",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/ai-video-generator",
        "x-requested-with": "mark.via.gp",
    })
    try:
        # Delay to look like human
        time.sleep(random.uniform(0.5, 1.5))
        session.post(f"{BASE_URL}/api/video/anon/identity", json={}, timeout=10)
    except:
        pass
    return session

@app.route('/')
def home():
    return "Raphael Backend is Running!"

@app.route('/api/generate', methods=['POST'])
def generate():
    # FIXED: Using request.files.get for the image
    prompt = request.form.get('prompt', '')
    image_file = request.files.get('image')

    if not prompt or not image_file:
        return jsonify({"status": "error", "message": "Prompt and image are required"})

    image_bytes = image_file.read()
    content_type = image_file.content_type or "image/jpeg"

    def generate_stream():
        try:
            yield "data: " + json.dumps({"log": "🔄 Initializing request..."}) + "\n\n"
            
            max_retries = 4
            ticket = None
            session = None
            client_req_id = str(uuid.uuid4())
            
            for attempt in range(max_retries):
                session = get_fresh_session()
                file_size = len(image_bytes)
                checksum_base64 = base64.b64encode(hashlib.sha256(image_bytes).digest()).decode()

                payload = {
                    "action": "prepare",
                    "model_id": "minimax-h3-turbo",
                    "resolution": "480p-low",
                    "client_request_id": client_req_id,
                    "media_type": "image",
                    "slot_name": "input-start",
                    "file": {"size": file_size, "type": content_type, "checksumSHA256": checksum_base64}
                }

                yield "data: " + json.dumps({"log": f"☁️ Preparing upload (Attempt {attempt+1}/{max_retries})..."}) + "\n\n"
                r = session.post(f"{BASE_URL}/api/video/upload-input", json=payload, timeout=15)
                data = r.json()

                if "uploadUrl" not in data:
                    yield "data: " + json.dumps({"log": f"❌ Upload prepare failed: {data}"}) + "\n\n"
                    time.sleep(3)
                    continue

                requests.put(data["uploadUrl"], data=image_bytes, headers=data["headers"], timeout=30)

                confirm_payload = {
                    "model_id": "minimax-h3-turbo",
                    "resolution": "480p-low",
                    "client_request_id": client_req_id,
                    "media_type": "image",
                    "slot_name": "input-start",
                    "action": "confirm",
                    "authorization": data["authorization"]
                }
                r = session.post(f"{BASE_URL}/api/video/upload-input", json=confirm_payload, timeout=15)
                img_data = r.json()

                yield "data: " + json.dumps({"log": "🎟️ Requesting generation ticket..."}) + "\n\n"
                ticket_payload = {
                    "prompt": prompt,
                    "aspect": "9:16",
                    "generate_audio": True,
                    "mode": "imageToVideo",
                    "image_urls": [img_data["url"]],
                    "media_sources": [{"mediaType": "image", "index": 0, "authorization": data["authorization"]}],
                    "client_request_id": client_req_id
                }
                r = session.post(f"{BASE_URL}/api/video/anon/ticket", json=ticket_payload, timeout=15)
                ticket_data = r.json()

                ticket = ticket_data.get("data", {}).get("ticket")
                wait_sec = ticket_data.get("data", {}).get("wait_ms", 80000) / 1000

                if ticket:
                    yield "data: " + json.dumps({"log": f"✅ Ticket acquired!"}) + "\n\n"
                    break 
                else:
                    yield "data: " + json.dumps({"log": f"⚠️ Limit hit. Changing identity, waiting 5s..."}) + "\n\n"
                    time.sleep(5)
            
            if not ticket:
                yield "data: " + json.dumps({"error": "Failed to bypass limit. Render IP is temporarily blocked."}) + "\n\n"
                return

            for remaining in range(int(wait_sec), 0, -5):
                yield "data: " + json.dumps({"log": f"⏳ Queue: waiting {remaining}s..."}) + "\n\n"
                time.sleep(min(5, remaining))

            yield "data: " + json.dumps({"log": "🎫 Redeeming ticket..."}) + "\n\n"
            r = session.post(f"{BASE_URL}/api/video/anon/redeem", json={"ticket": ticket}, timeout=15)
            while r.status_code == 409:
                wait_ms = r.json().get("data", {}).get("wait_ms", 15000)
                yield "data: " + json.dumps({"log": f"⏳ Server busy. Waiting {int(wait_ms/1000)}s..."}) + "\n\n"
                time.sleep(wait_ms / 1000)
                r = session.post(f"{BASE_URL}/api/video/anon/redeem", json={"ticket": ticket}, timeout=15)

            redeem_data = r.json()
            job_id = redeem_data.get("data", {}).get("job_id")

            if not job_id:
                yield "data: " + json.dumps({"error": "Redeem failed"}) + "\n\n"
                return

            yield "data: " + json.dumps({"log": f"🎬 Rendering video (Job: {job_id})..."}) + "\n\n"
            last_progress = -1
            while True:
                r = session.get(f"{BASE_URL}/api/video/anon/job/{job_id}", timeout=15)
                job_data = r.json().get("data", {})
                status = job_data.get("status")
                progress = job_data.get("progress", 0)

                if status == "complete":
                    tasks = job_data.get("tasks", [])
                    if tasks and "videoUrl" in tasks[0].get("assets", {}):
                        video_url = tasks[0]["assets"]["videoUrl"]
                        yield "data: " + json.dumps({"log": f"🎉 Success!"}) + "\n\n"
                        yield "data: " + json.dumps({"success": video_url}) + "\n\n"
                        return
                elif status == "failed":
                    yield "data: " + json.dumps({"error": "Rendering failed"}) + "\n\n"
                    return

                if progress != last_progress:
                    yield "data: " + json.dumps({"log": f"🎬 Rendering: {progress}%"}) + "\n\n"
                    last_progress = progress

                time.sleep(3)

        except Exception as e:
            yield "data: " + json.dumps({"error": str(e)}) + "\n\n"

    return Response(generate_stream(), mimetype="text/event-stream")

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
