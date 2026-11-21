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

# --- RANDOM BROWSER PROFILES ---
BROWSERS = [
    {
        "user-agent": "Mozilla/5.0 (Linux; Android 15; I2301 Build/AP3A.240905.015.A2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.8103.50 Mobile Safari/537.36",
        "sec-ch-ua": '"Not-A.Brand";v="99", "Android WebView";v="157", "Chromium";v="157"',
        "x-requested-with": "mark.via.gp",
        "sec-ch-ua-platform": '"Android"',
        "sec-ch-ua-mobile": "?1"
    },
    {
        "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
        "sec-ch-ua": '"Apple WebKit";v="605", "Safari";v="17"',
        "x-requested-with": "com.apple.mobilesafari",
        "sec-ch-ua-platform": '"iOS"',
        "sec-ch-ua-mobile": "?1"
    },
    {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
        "x-requested-with": "XMLHttpRequest",
        "sec-ch-ua-platform": '"Windows"',
        "sec-ch-ua-mobile": "?0"
    },
    {
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
        "x-requested-with": "XMLHttpRequest",
        "sec-ch-ua-platform": '"macOS"',
        "sec-ch-ua-mobile": "?0"
    },
    {
        "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Mobile Safari/537.36",
        "sec-ch-ua": '"Chromium";v="154", "Google Chrome";v="154", "Not A(Brand";v="99"',
        "x-requested-with": "mark.via.gp",
        "sec-ch-ua-platform": '"Android"',
        "sec-ch-ua-mobile": "?1"
    }
]

def get_fresh_session():
    """Generates a new cookie AND picks a random browser profile."""
    # Pick a random browser
    browser = random.choice(BROWSERS)
    
    session = requests.Session()
    session.headers.update({
        "User-Agent": browser["user-agent"],
        "Accept": "*/*",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/ai-video-generator",
        "sec-ch-ua": browser["sec-ch-ua"],
        "sec-ch-ua-platform": browser["sec-ch-ua-platform"],
        "sec-ch-ua-mobile": browser["sec-ch-ua-mobile"],
        "x-requested-with": browser["x-requested-with"]
    })
    
    # Get new identity (New Cookie)
    session.post(f"{BASE_URL}/api/video/anon/identity", json={}, timeout=10)
    return session

@app.route('/')
def home():
    return "Raphael Backend is Running!"

@app.route('/api/generate', methods=['POST'])
def generate():
    prompt = request.form.get('prompt', '')
    image_file = request.files.get('image')

    if not prompt or not image_file:
        return jsonify({"status": "error", "message": "Prompt and image are required"})

    # Read file immediately to prevent I/O closed file error
    image_bytes = image_file.read()
    content_type = image_file.content_type or "image/jpeg"

    def generate_stream():
        try:
            yield "data: " + json.dumps({"log": "🔄 Picking random browser & generating new identity..."}) + "\n\n"
            session = get_fresh_session()

            # 1. Prepare Upload
            file_size = len(image_bytes)
            checksum_base64 = base64.b64encode(hashlib.sha256(image_bytes).digest()).decode()
            client_req_id = str(uuid.uuid4())

            payload = {
                "action": "prepare",
                "model_id": "minimax-h3-turbo",
                "resolution": "480p-low",
                "client_request_id": client_req_id,
                "media_type": "image",
                "slot_name": "input-start",
                "file": {"size": file_size, "type": content_type, "checksumSHA256": checksum_base64}
            }

            yield "data: " + json.dumps({"log": "☁️ Preparing upload..."}) + "\n\n"
            r = session.post(f"{BASE_URL}/api/video/upload-input", json=payload, timeout=15)
            data = r.json()
            yield "data: " + json.dumps({"log": f"Raw: {data}"}) + "\n\n"

            if "uploadUrl" not in data:
                yield "data: " + json.dumps({"error": f"Upload prepare failed: {data}"}) + "\n\n"
                return

            # 2. Upload to R2
            yield "data: " + json.dumps({"log": "📤 Uploading image to R2..."}) + "\n\n"
            requests.put(data["uploadUrl"], data=image_bytes, headers=data["headers"], timeout=30)

            # 3. Confirm Upload
            yield "data: " + json.dumps({"log": "✅ Confirming upload..."}) + "\n\n"
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
            yield "data: " + json.dumps({"log": f"Raw: {img_data}"}) + "\n\n"

            if "url" not in img_data:
                yield "data: " + json.dumps({"error": f"Confirm failed: {img_data}"}) + "\n\n"
                return

            # 4. Ticket
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
            yield "data: " + json.dumps({"log": f"Raw: {ticket_data}"}) + "\n\n"

            ticket = ticket_data.get("data", {}).get("ticket")
            wait_sec = ticket_data.get("data", {}).get("wait_ms", 80000) / 1000

            if not ticket:
                yield "data: " + json.dumps({"error": "Ticket failed"}) + "\n\n"
                return

            # 5. Wait
            for remaining in range(int(wait_sec), 0, -5):
                yield "data: " + json.dumps({"log": f"⏳ Queue: waiting {remaining}s..."}) + "\n\n"
                time.sleep(min(5, remaining))

            # 6. Redeem
            yield "data: " + json.dumps({"log": "🎫 Redeeming ticket..."}) + "\n\n"
            r = session.post(f"{BASE_URL}/api/video/anon/redeem", json={"ticket": ticket}, timeout=15)
            while r.status_code == 409:
                wait_ms = r.json().get("data", {}).get("wait_ms", 15000)
                yield "data: " + json.dumps({"log": f"⏳ Server busy. Waiting {int(wait_ms/1000)}s..."}) + "\n\n"
                time.sleep(wait_ms / 1000)
                r = session.post(f"{BASE_URL}/api/video/anon/redeem", json={"ticket": ticket}, timeout=15)

            redeem_data = r.json()
            yield "data: " + json.dumps({"log": f"Raw: {redeem_data}"}) + "\n\n"
            job_id = redeem_data.get("data", {}).get("job_id")

            if not job_id:
                yield "data: " + json.dumps({"error": "Redeem failed"}) + "\n\n"
                return

            # 7. Poll
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
                        yield "data: " + json.dumps({"log": f"🎉 Success! {video_url}"}) + "\n\n"
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
