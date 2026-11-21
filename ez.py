import os
import time
import json
import uuid
import hashlib
import base64
import requests
from flask import Flask, request, jsonify, Response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

BASE_URL = "https://raphael.app"
USER_AGENT = "Mozilla/5.0 (Linux; Android 15; I2301 Build/AP3A.240905.015.A2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.8103.50 Mobile Safari/537.36"

def get_fresh_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/ai-video-generator",
        "x-requested-with": "mark.via.gp",
    })
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

    def generate_stream():
        try:
            yield "data: " + json.dumps({"log": "🔄 Generating new identity (Bypassing limit)..."}) + "\n\n"
            session = get_fresh_session()

            # 1. Prepare Upload
            file_data = image_file.read()
            file_size = len(file_data)
            checksum_base64 = base64.b64encode(hashlib.sha256(file_data).digest()).decode()
            client_req_id = str(uuid.uuid4())

            payload = {
                "action": "prepare",
                "model_id": "minimax-h3-turbo",
                "resolution": "480p-low",
                "client_request_id": client_req_id,
                "media_type": "image",
                "slot_name": "input-start",
                "file": {"size": file_size, "type": "image/jpeg", "checksumSHA256": checksum_base64}
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
            requests.put(data["uploadUrl"], data=file_data, headers=data["headers"], timeout=30)

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
