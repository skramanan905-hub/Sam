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

video_cache = {}
conversation_images = {} 

def monitor_generation(conv_id, task_id):
    wait_time = 0
    while wait_time < 1200:
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
                    video_cache[task_id]["status"] = "success"
                    video_cache[task_id]["url"] = msg["data"]["data"]["results"][0]["url"]
                    return
                elif msg["type"] == "GenerationFailed" and msg["data"].get("task_id") == task_id:
                    video_cache[task_id]["status"] = "failed"
                    video_cache[task_id]["error"] = msg["data"].get("error_message", "Queue is full")
                    return
        except Exception:
            pass
    
    if task_id in video_cache and video_cache[task_id]["status"] == "queued":
        video_cache[task_id]["status"] = "timeout"

@app.route('/')
def home():
    return "Pavo Backend is Active!"

@app.route('/api/generate', methods=['POST'])
def generate():
    try:
        d = request.json
        prompt = d.get("prompt")
        duration = int(d.get("duration", 12))
        ratio = d.get("ratio", "9:16")
        image_url = d.get("image_url")
        existing_conv_id = d.get("conv_id") 
        
        if existing_conv_id:
            conv_id = existing_conv_id
            if not image_url and conv_id in conversation_images:
                image_url = conversation_images[conv_id]
        else:
            conv_url = f"{API_BASE}/api/v1/chat/conversation"
            r_conv = requests.post(conv_url, json={"title": prompt[:60], "folder_id": "", "kb_strict": False}, headers=get_headers(), timeout=20)
            conv_data = safe_json(r_conv)
            try:
                conv_id = conv_data["data"]["conversation_id"]
            except KeyError:
                return jsonify({"status": "error", "message": f"API Error: {conv_data}"})

        if image_url:
            conversation_images[conv_id] = image_url

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
        # 🔥 CAPTURE THE ASSISTANT TEXT FROM THE STREAM
        stream_text = "I am starting to prepare your creation..."
        
        with requests.post(stream_url, json=payload, headers={**get_headers(), "accept": "text/event-stream"}, stream=True, timeout=30) as r:
            for line in r.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith("data:"):
                        try:
                            evt = json.loads(line_str[5:].strip())
                            # Capture text messages
                            if evt.get("type") == "MessageDelta" and "content" in evt.get("data", {}):
                                stream_text = evt["data"]["content"]
                            elif evt.get("type") == "GenerationStart":
                                task_id = evt.get("task_id")
                                break
                            elif evt.get("type") in ["GenerationFailed", "PromptSafetyBlocked"]:
                                return jsonify({"status": "error", "message": evt.get("data", {}).get("error_message", "Failed"), "text": stream_text})
                        except: pass

        if not task_id:
            return jsonify({"status": "error", "message": "Failed to start generation stream.", "text": stream_text})

        video_cache[task_id] = {"status": "queued", "conv_id": conv_id, "text": stream_text}
        threading.Thread(target=monitor_generation, args=(conv_id, task_id), daemon=True).start()

        return jsonify({"status": "success", "task_id": task_id, "conv_id": conv_id, "text": stream_text})

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
        r_pre = requests.post(pre_url, json={"purpose": "chat_attachment", "content_type": "image/jpeg", "filename": "upload.jpg"}, headers=get_headers(), timeout=20)
        pre_data = safe_json(r_pre)
        requests.put(pre_data["data"]["upload_url"], data=file.read(), headers={"Content-Type": "image/jpeg"}, timeout=20)
        requests.post(f"{API_BASE}/api/v1/file/inspect", json={"content_type": "image/jpeg", "url": pre_data["data"]["public_url"]}, headers=get_headers(), timeout=20)
        return jsonify({"status": "success", "url": pre_data["data"]["public_url"]})
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
        saved_img = conversation_images.get(conv_id, None)

        for turn in data.get("data", {}).get("turns", []):
            prompt = "Unknown"
            for u_msg in turn.get("user", []):
                if u_msg.get("type") == "Message":
                    prompt = u_msg["data"].get("content", prompt)
                elif u_msg.get("type") == "File" and not saved_img:
                    saved_img = u_msg["data"].get("url")
            
            # Extract failed text if it exists in history
            asst_text = ""
            for a_msg in turn.get("assistant", []):
                if a_msg["type"] == "Message":
                    asst_text = a_msg["data"].get("content", "")
                elif a_msg["type"] == "GenerationSuccess":
                    res = a_msg["data"]["data"]["results"]
                    if res and res[0].get("url"):
                        videos.append({"url": res[0]["url"], "prompt": prompt, "image_url": saved_img, "text": asst_text})
                elif a_msg["type"] == "GenerationFailed":
                    err = a_msg["data"].get("error_message", "Queue is full")
                    videos.append({"url": None, "prompt": prompt, "image_url": saved_img, "text": asst_text, "error": err})
                        
        return jsonify({"status": "success", "videos": videos})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
