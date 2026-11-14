import os
import json
import time
import requests
import threading
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

API_BASE = "https://api.pixa-ai.work"

def get_headers(token):
    return {
        "x-platform": "1", "x-user-language": "en", "x-app-timezone": "Asia/Calcutta",
        "origin": "https://app.pavo-ai.work", "referer": "https://app.pavo-ai.work/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "content-type": "application/json", "accept": "*/*",
        "authorization": f"Bearer {token}"
    }

def safe_json(r):
    try:
        return r.json()
    except Exception:
        return {"_raw": r.text, "_status": r.status_code}

video_cache = {}
conversation_images = {}

def check_task_in_history(conv_id, task_id, token):
    url = f"{API_BASE}/api/v1/chat/conversation/history?conversation_id={conv_id}"
    r = requests.get(url, headers=get_headers(token), timeout=20)
    data = safe_json(r)

    # FIX: turns is inside data["data"]["turns"]
    turns = data.get("data", {}).get("turns", [])
    if not turns:
        return None

    for turn in reversed(turns):
        for msg in turn.get("assistant", []):
            m_type = msg.get("type")
            m_data = msg.get("data", {})
            if m_type == "GenerationSuccess" and m_data.get("task_id") == task_id:
                results = m_data.get("data", {}).get("results", [])
                if results and results[0].get("url"):
                    return {"status": "success", "url": results[0]["url"]}
            elif m_type == "GenerationFailed" and m_data.get("task_id") == task_id:
                err = m_data.get("error_message") or m_data.get("error") or "Queue is full"
                return {"status": "failed", "error": err}
            elif m_type == "PromptSafetyBlocked":
                err = m_data.get("error_message") or m_data.get("error") or "Prompt blocked"
                return {"status": "failed", "error": err}
    return None

def monitor_generation(conv_id, task_id, token):
    wait_time = 0
    while wait_time < 1200:
        time.sleep(10)
        wait_time += 10
        try:
            res = check_task_in_history(conv_id, task_id, token)
            if res:
                video_cache[task_id].update(res)
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
        token = d.get("token")
        if not token:
            return jsonify({"status": "error", "message": "JWT Token is required"})

        prompt = d.get("prompt", "")
        duration = int(d.get("duration", 12))
        ratio = d.get("ratio", "9:16")
        image_url = d.get("image_url")
        existing_conv_id = d.get("conv_id")
        is_spam = bool(d.get("is_spam", False))

        # FIX: In spam mode, ALWAYS create a brand-new conversation
        if existing_conv_id and not is_spam:
            conv_id = existing_conv_id
            if not image_url and conv_id in conversation_images:
                image_url = conversation_images[conv_id]
        else:
            conv_url = f"{API_BASE}/api/v1/chat/conversation"
            title_json = json.dumps([{"type": "text", "content": prompt[:60]}])
            r_conv = requests.post(
                conv_url,
                json={"title": title_json, "folder_id": "", "kb_strict": False},
                headers=get_headers(token),
                timeout=20
            )
            conv_data = safe_json(r_conv)
            try:
                conv_id = conv_data["data"]["conversation_id"]
            except KeyError:
                return jsonify({"status": "error", "message": f"Invalid Token or API Error: {conv_data}"})

        if image_url:
            conversation_images[conv_id] = image_url

        stream_url = f"{API_BASE}/api/v1/chat/stream"
        payload = {
            "conversation_id": conv_id,
            "prompt": prompt,
            "mode": "omni_to_video",
            "model": "agnes-video-new-flash",
            "ratio": ratio,
            "duration": duration,
            "resolution": "hd",
            "sound": True,
            "creative_prompt_json": json.dumps([{"type": "text", "content": prompt}]),
        }
        if image_url:
            payload["images"] = [{
                "url": image_url,
                "meta_data": {
                    "original_filename": "input.jpg",
                    "content_type": "image/jpeg",
                    "purpose": "chat_attachment"
                }
            }]

        task_id = None
        stream_text = "I am starting to prepare your creation..."

        with requests.post(
            stream_url,
            json=payload,
            headers={**get_headers(token), "accept": "text/event-stream"},
            stream=True,
            timeout=60
        ) as r:
            if r.status_code != 200:
                return jsonify({"status": "error", "message": f"Stream HTTP {r.status_code}: {r.text[:200]}"})

            for line in r.iter_lines():
                if not line:
                    continue
                line_str = line.decode('utf-8', errors='ignore')
                if line_str.startswith("data:"):
                    try:
                        evt = json.loads(line_str[5:].strip())
                        etype = evt.get("type")
                        if etype == "MessageDelta" and "content" in evt.get("data", {}):
                            stream_text = evt["data"]["content"]
                        elif etype == "GenerationStart":
                            task_id = evt.get("task_id")
                            break
                        elif etype in ["GenerationFailed", "PromptSafetyBlocked"]:
                            err_msg = (
                                evt.get("data", {}).get("error_message")
                                or evt.get("data", {}).get("error")
                                or evt.get("error_message")
                                or evt.get("error")
                                or "Failed"
                            )
                            return jsonify({"status": "error", "message": err_msg, "text": stream_text})
                    except Exception:
                        pass

        if not task_id:
            return jsonify({"status": "error", "message": "Failed to start generation stream.", "text": stream_text})

        video_cache[task_id] = {"status": "queued", "conv_id": conv_id, "text": stream_text}
        threading.Thread(target=monitor_generation, args=(conv_id, task_id, token), daemon=True).start()

        return jsonify({"status": "success", "task_id": task_id, "conv_id": conv_id, "text": stream_text})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/status/<task_id>', methods=['GET'])
def check_status(task_id):
    cached = video_cache.get(task_id)
    if cached and cached.get("status") != "queued":
        return jsonify(cached)

    # Fallback: directly check Pixa history if cache was missed (e.g. Render restart / multi-worker)
    conv_id = request.args.get("conv_id") or (cached.get("conv_id") if cached else None)
    token = request.headers.get("X-Pavo-Token")
    if conv_id and token:
        try:
            res = check_task_in_history(conv_id, task_id, token)
            if res:
                video_cache[task_id] = {**(cached or {}), **res, "conv_id": conv_id}
                return jsonify(video_cache[task_id])
            return jsonify({"status": "queued", "conv_id": conv_id})
        except Exception:
            pass

    return jsonify(cached or {"status": "not_found"})

@app.route('/api/upload', methods=['POST'])
def upload():
    try:
        token = request.form.get("token")
        if not token:
            return jsonify({"status": "error", "message": "Token required"})
        if 'image' not in request.files:
            return jsonify({"status": "error", "message": "No file"})

        file = request.files['image']
        ctype = file.content_type if file.content_type in ("image/jpeg", "image/png", "image/webp") else "image/jpeg"
        fname = file.filename or "upload.jpg"

        pre_url = f"{API_BASE}/api/v1/file/presigned-url"
        r_pre = requests.post(
            pre_url,
            json={"purpose": "chat_attachment", "content_type": ctype, "filename": fname},
            headers=get_headers(token),
            timeout=20
        )
        pre_data = safe_json(r_pre)
        requests.put(pre_data["data"]["upload_url"], data=file.read(), headers={"Content-Type": ctype}, timeout=30)
        requests.post(
            f"{API_BASE}/api/v1/file/inspect",
            json={"content_type": ctype, "url": pre_data["data"]["public_url"]},
            headers=get_headers(token),
            timeout=20
        )
        return jsonify({"status": "success", "url": pre_data["data"]["public_url"]})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/history', methods=['GET'])
def get_projects():
    try:
        token = request.headers.get("X-Pavo-Token")
        if not token:
            return jsonify({"status": "error", "message": "Token missing in headers"})

        r = requests.get(f"{API_BASE}/api/v1/chat/projects?page_size=50&page=1", headers=get_headers(token), timeout=20)
        data = safe_json(r)
        return jsonify({"status": "success", "projects": data.get("data", {}).get("list", [])})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/videos/<conv_id>', methods=['GET'])
def get_videos(conv_id):
    try:
        token = request.headers.get("X-Pavo-Token")
        if not token:
            return jsonify({"status": "error", "message": "Token missing in headers"})

        r = requests.get(f"{API_BASE}/api/v1/chat/conversation/history?conversation_id={conv_id}", headers=get_headers(token), timeout=20)
        data = safe_json(r)
        videos = []
        saved_img = conversation_images.get(conv_id, None)

        for turn in data.get("data", {}).get("turns", []):
            prompt = "Unknown"
            turn_img = saved_img
            for u_msg in turn.get("user", []):
                if u_msg.get("type") == "Message":
                    prompt = u_msg["data"].get("content", prompt)
                elif u_msg.get("type") == "File":
                    turn_img = u_msg["data"].get("url") or turn_img

            asst_text = ""
            task_id = None
            found_terminal = False

            for a_msg in turn.get("assistant", []):
                atype = a_msg.get("type")
                adata = a_msg.get("data", {})
                if atype == "Message":
                    asst_text = adata.get("content", "")
                elif atype == "GenerationStart":
                    task_id = adata.get("task_id")
                elif atype == "GenerationSuccess":
                    res = adata.get("data", {}).get("results", [])
                    if res and res[0].get("url"):
                        videos.append({
                            "status": "success",
                            "url": res[0]["url"],
                            "prompt": prompt,
                            "image_url": turn_img,
                            "text": asst_text
                        })
                        found_terminal = True
                elif atype in ["GenerationFailed", "PromptSafetyBlocked"]:
                    err = adata.get("error_message") or adata.get("error") or "Queue is full"
                    videos.append({
                        "status": "failed",
                        "url": None,
                        "prompt": prompt,
                        "image_url": turn_img,
                        "text": asst_text,
                        "error": err
                    })
                    found_terminal = True

            # FIX: Include turns that are still generating
            if not found_terminal:
                videos.append({
                    "status": "processing",
                    "task_id": task_id,
                    "url": None,
                    "prompt": prompt,
                    "image_url": turn_img,
                    "text": asst_text or "I am starting to prepare your creation..."
                })

        return jsonify({"status": "success", "videos": videos})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/delete_project', methods=['POST'])
def delete_project():
    try:
        d = request.json
        token = d.get("token")
        conv_id = d.get("conv_id")

        url = f"{API_BASE}/api/v1/chat/projects?id={conv_id}&type=ai_creation"
        r = requests.delete(url, headers=get_headers(token), timeout=20)
        data = safe_json(r)

        if data.get("code") == "000000":
            return jsonify({"status": "success"})
        else:
            return jsonify({"status": "error", "message": data.get("message", "Unknown error")})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
