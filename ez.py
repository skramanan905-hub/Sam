import os
import time
import json
import uuid
import hashlib
import base64
import random
import string
import threading
from curl_cffi import requests 
from flask import Flask, request, jsonify, Response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

BASE_URL = "https://raphael.app"
PROXY_FILE = "proxies.txt" # Make sure this file is in the same folder

# --- PROXY MANAGER ---
class ProxyManager:
    def __init__(self):
        self.proxies = []
        self.load_proxies()

    def load_proxies(self):
        print("🔄 Loading proxies from file...")
        try:
            with open(PROXY_FILE, 'r') as f:
                lines = f.readlines()
                self.proxies = [line.strip() for line in lines if line.strip()]
            print(f"✅ Loaded {len(self.proxies)} proxies.")
        except Exception as e:
            print(f"❌ Error loading proxies: {e}")

    def get_working_proxy(self):
        """Tries proxies until one works. Shuffles to avoid dead IPs."""
        if not self.proxies:
            self.load_proxies()
            
        proxies_to_test = list(self.proxies)
        random.shuffle(proxies_to_test)

        for proxy in proxies_to_test:
            # Clean up format
            if not proxy.startswith("http"):
                if proxy.startswith("socks"):
                    continue # curl_cffi handles socks poorly sometimes, skip if possible
                proxy = f"http://{proxy}"
            
            try:
                # Test proxy quickly
                test_session = requests.Session()
                test_session.proxies = {"http": proxy, "https": proxy}
                # Test against Raphael's domain to ensure Cloudflare accepts it
                r = test_session.get(f"{BASE_URL}/api/video/anon/identity", timeout=5, impersonate="chrome")
                if r.status_code == 200:
                    print(f"✅ Found working proxy: {proxy}")
                    return proxy
            except Exception:
                continue
        
        print("❌ No working proxies found in list.")
        return None

proxy_manager = ProxyManager()

# --- SESSION GENERATOR ---
def generate_random_string(length=20):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def get_fresh_session():
    session = requests.Session()
    
    proxy = proxy_manager.get_working_proxy()
    if not proxy:
        raise Exception("Could not find a working proxy. The free list might be exhausted. Try again later.")
    
    session.proxies = {"http": proxy, "https": proxy}
    
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Linux; Android 15; I2301 Build/AP3A.240905.015.A2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.8103.50 Mobile Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/ai-video-generator",
        "x-requested-with": "mark.via.gp",
        "sec-ch-ua": '"Not-A.Brand";v="99", "Android WebView";v="157", "Chromium";v="157"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty"
    })

    fake_clck = f"18e0{generate_random_string(4)}%5E2%5Egbc%5E0%5E2516"
    fake_clsk = f"{generate_random_string(10)}%5E1795265175352%5E1%5E1%5Eu.clarity.ms%2Fcollect"
    
    session.cookies.set("_clck", fake_clck)
    session.cookies.set("_clsk", fake_clsk)

    session.post(
        f"{BASE_URL}/api/video/anon/identity", 
        json={}, 
        timeout=15,
        impersonate="chrome" 
    )
    
    return session

# --- FLASK APP ---
@app.route('/')
def home():
    return "Raphael Backend is Running with Proxies!"

@app.route('/api/generate', methods=['POST'])
def generate():
    prompt = request.form.get('prompt', '')
    image_file = request.files.get('image')

    if not prompt or not image_file:
        return jsonify({"status": "error", "message": "Prompt and image are required"})

    image_bytes = image_file.read()
    content_type = image_file.content_type or "image/jpeg"

    def generate_stream():
        try:
            yield "data: " + json.dumps({"log": "🔄 Finding working proxy..."}) + "\n\n"
            session = get_fresh_session()
            
            yield "data: " + json.dumps({"log": "✅ Proxy found! Generating identity..."}) + "\n\n"

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
            r = session.post(f"{BASE_URL}/api/video/upload-input", json=payload, timeout=15, impersonate="chrome")
            data = r.json()
            yield "data: " + json.dumps({"log": f"Raw: {data}"}) + "\n\n"

            if "uploadUrl" not in data:
                yield "data: " + json.dumps({"error": f"Upload prepare failed: {data}"}) + "\n\n"
                return

            # 2. Upload to R2
            yield "data: " + json.dumps({"log": "📤 Uploading image to R2..."}) + "\n\n"
            r = session.put(data["uploadUrl"], data=image_bytes, headers=data["headers"], timeout=30, impersonate="chrome")

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
            r = session.post(f"{BASE_URL}/api/video/upload-input", json=confirm_payload, timeout=15, impersonate="chrome")
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
            r = session.post(f"{BASE_URL}/api/video/anon/ticket", json=ticket_payload, timeout=15, impersonate="chrome")
            ticket_data = r.json()
            yield "data: " + json.dumps({"log": f"Raw: {ticket_data}"}) + "\n\n"

            ticket = ticket_data.get("data", {}).get("ticket")
            wait_sec = ticket_data.get("data", {}).get("wait_ms", 80000) / 1000

            if not ticket:
                yield "data: " + json.dumps({"error": "Ticket failed. ANON_DAILY_LIMIT hit on this proxy."}) + "\n\n"
                return

            # 5. Wait
            for remaining in range(int(wait_sec), 0, -5):
                yield "data: " + json.dumps({"log": f"⏳ Queue: waiting {remaining}s..."}) + "\n\n"
                time.sleep(min(5, remaining))

            # 6. Redeem
            yield "data: " + json.dumps({"log": "🎫 Redeeming ticket..."}) + "\n\n"
            r = session.post(f"{BASE_URL}/api/video/anon/redeem", json={"ticket": ticket}, timeout=15, impersonate="chrome")
            
            while r.status_code == 409:
                wait_ms = r.json().get("data", {}).get("wait_ms", 15000)
                yield "data: " + json.dumps({"log": f"⏳ Server busy. Waiting {int(wait_ms/1000)}s..."}) + "\n\n"
                time.sleep(wait_ms / 1000)
                r = session.post(f"{BASE_URL}/api/video/anon/redeem", json={"ticket": ticket}, timeout=15, impersonate="chrome")

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
                r = session.get(f"{BASE_URL}/api/video/anon/job/{job_id}", timeout=15, impersonate="chrome")
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
