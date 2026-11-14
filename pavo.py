import os
import json
import time
import requests
import threading
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ================= CONFIGURATION =================
API_BASE = "https://api.pixa-ai.work"
PIXA_JWT_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxYTA2YTE2NC0zY2FjLTQzY2QtODM5YS01ZTM4ZTE2NTViZmIiLCJleHAiOjE3OTcwNDU5MDcsIm5iZiI6MTc5NDYyNjcwNywiaWF0IjoxNzk0NjI2NzA3fQ.rExyu1j6MLIMVV8Tl2RW5QBBtBTuqcgLgxAiaHof5Wo"

def get_headers():
    return {
        "x-platform": "1", "x-user-language": "en", "x-app-timezone": "Asia/Calcutta",
        "origin": "https://app.pavo-ai.work", "referer": "https://app.pavo-ai.work/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "content-type": "application/json", "accept": "*/*",
        "authorization": f"Bearer {PIXA_JWT_TOKEN}"
    }

def safe_json(r):
    try: return r.json()
    except: return {"_raw": r.text, "_status": r.status_code}

# Caches
video_cache = {}
conversation_images = {} # Remembers image for Regenerate

# ================= MONITOR THREAD =================
def monitor_generation(conv_id, task_id):
    wait_time = 0
    while wait_time < 1200: # 20 mins max
        time.sleep(10)
        wait_time += 10
        try:
            url = f"{API_BASE}/api/v1/chat/conversation/history?conversation_id={conv_id}"
            r = requests.get(url, headers=get_headers(), timeout=20)
            data = safe_json(r)
            
            turns = data.get("turns", [])
            if not turns: continue
            
            last_turn = turns[-1]
            for msg in last_turn.get("assistant", []):
                if msg["type"] == "GenerationSuccess" and msg["data"].get("task_id") == task_id:
                    video_cache[task_id] = {
                        "status": "success",
                        "url": msg["data"]["data"]["results"][0]["url"],
                        "prompt": msg["data"].get("prompt", ""),
                        "conv_id": conv_id
                    }
                    return
                elif msg["type"] == "GenerationFailed" and msg["data"].get("task_id") == task_id:
                    err_msg = msg["data"].get("error_message", "Queue is full")
                    video_cache[task_id] = {"status": "failed", "error": err_msg}
                    return
        except Exception:
            pass
    
    if task_id not in video_cache:
        video_cache[task_id] = {"status": "timeout", "error": "Timed out after 20 minutes"}

# ================= ROUTES =================

@app.route('/')
def home():
    return "Pavo Backend is Active! (Do not close this tab, your API is running here)."

@app.route('/api/generate', methods=['POST'])
def generate():
    try:
        d = request.json
        prompt = d.get("prompt")
        duration = int(d.get("duration", 12))
        ratio = d.get("ratio", "9:16")
        image_url = d.get("image_url")
        
        # 1. Create Conversation
        conv_url = f"{API_BASE}/api/v1/chat/conversation"
        conv_payload = {"title": prompt[:60], "folder_id": "", "kb_strict": False}
        r_conv = requests.post(conv_url, json=conv_payload, headers=get_headers(), timeout=20)
        conv_data = safe_json(r_conv)
        
        # FIX: Safely get conversation_id
        try:
            conv_id = conv_data["data"]["conversation_id"]
        except KeyError:
            return jsonify({"status": "error", "message": f"API Error: {conv_data}"})

        # Save image to memory for regeneration
        if image_url:
            conversation_images[conv_id] = image_url

        # 2. Start Video Generation
        stream_url = f"{API_BASE}/api/v1/chat/stream"
        payload = {
            "conversation_id": conv_id, "prompt": prompt, "mode": "omni_to_video",
            "model": "agnes-video-new-flash", "ratio": ratio, "duration": duration,
            "resolution": "hd", "sound": True,
            "creative_prompt_json": json.dumps([{"type": "text", "content": prompt}]),
            "images": []
        }
        if image_url:
            payload["images"].append({"url": image_url, "meta_data": {"original_filename": "input.jpg", "content_type": "image/jpeg", "purpose": "chat_attachment"}})

        task_id = None
        with requests.post(stream_url, json=payload, headers={**get_headers(), "accept": "text/event-stream"}, stream=True, timeout=30) as r:
            for line in r.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith("data:"):
                        try:
                            evt = json.loads(line_str[5:].strip())
                            if evt.get("type") == "GenerationStart":
                                task_id = evt.get("task_id")
                                break
                            elif evt.get("type") in ["GenerationFailed", "PromptSafetyBlocked"]:
                                return jsonify({"status": "error", "message": evt.get("data", {}).get("error_message", "Failed")})
                        except: pass

        if not task_id:
            return jsonify({"status": "error", "message": "Failed to start generation stream."})

        video_cache[task_id] = {"status": "queued"}
        threading.Thread(target=monitor_generation, args=(conv_id, task_id), daemon=True).start()

        return jsonify({"status": "success", "task_id": task_id, "conv_id": conv_id})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/status/<task_id>', methods=['GET'])
def check_status(task_id):
    return jsonify(video_cache.get(task_id, {"status": "not_found"}))

@app.route('/api/upload', methods=['POST'])
def upload():
    try:
        if 'image' not in request.files:
            return jsonify({"status": "error", "message": "No file"})
        file = request.files['image']
        
        pre_url = f"{API_BASE}/api/v1/file/presigned-url"
        pre_payload = {"purpose": "chat_attachment", "content_type": "image/jpeg", "filename": "upload.jpg"}
        r_pre = requests.post(pre_url, json=pre_payload, headers=get_headers(), timeout=20)
        pre_data = safe_json(r_pre)
        
        upload_url = pre_data["data"]["upload_url"]
        public_url = pre_data["data"]["public_url"]

        requests.put(upload_url, data=file.read(), headers={"Content-Type": "image/jpeg"}, timeout=20)
        
        inspect_url = f"{API_BASE}/api/v1/file/inspect"
        inspect_payload = {"content_type": "image/jpeg", "url": public_url}
        requests.post(inspect_url, json=inspect_payload, headers=get_headers(), timeout=20)

        return jsonify({"status": "success", "url": public_url})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/history', methods=['GET'])
def get_projects():
    try:
        r = requests.get(f"{API_BASE}/api/v1/chat/projects?page_size=50&page=1", headers=get_headers(), timeout=20)
        data = safe_json(r)
        return jsonify({"status": "success", "projects": data["data"].get("list", [])})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/videos/<conv_id>', methods=['GET'])
def get_videos(conv_id):
    try:
        r = requests.get(f"{API_BASE}/api/v1/chat/conversation/history?conversation_id={conv_id}", headers=get_headers(), timeout=20)
        data = safe_json(r)
        videos = []
        
        # Check if we have an image saved for this conv
        saved_img = conversation_images.get(conv_id, None)

        for turn in data.get("data", {}).get("turns", []):
            prompt = "Unknown"
            for u_msg in turn.get("user", []):
                if u_msg.get("type") == "Message":
                    prompt = u_msg["data"].get("content", prompt)
            
            for a_msg in turn.get("assistant", []):
                if a_msg["type"] == "GenerationSuccess":
                    res = a_msg["data"]["data"]["results"]
                    if res and res[0].get("url"):
                        videos.append({"url": res[0]["url"], "prompt": prompt, "image_url": saved_img})
                        
        return jsonify({"status": "success", "videos": videos})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
