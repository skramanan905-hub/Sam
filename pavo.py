import os
import json
import time
import threading
from flask import Flask, request, jsonify
from flask_cors import CORS

# Use curl_cffi (Chrome TLS fingerprint) if installed, otherwise fallback to requests
try:
    from curl_cffi import requests as http_client
    USE_CURL_CFFI = True
except ImportError:
    import requests as http_client
    USE_CURL_CFFI = False

app = Flask(__name__)
CORS(app)

API_BASE = "https://api.pixa-ai.work"
PROXY_URL = os.environ.get("PROXY_URL", "").strip()
PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None

def req(method, url, **kwargs):
    if USE_CURL_CFFI:
        kwargs.setdefault("impersonate", "chrome")
    if PROXIES:
        kwargs.setdefault("proxies", PROXIES)
    return getattr(http_client, method)(url, **kwargs)

def get_headers(token):
    return {
        "x-platform": "1",
        "x-user-language": "en",
        "x-app-timezone": "Asia/Calcutta",
        "x-client-time-ms": str(int(time.time() * 1000)),
        "origin": "https://app.pavo-ai.work",
        "referer": "https://app.pavo-ai.work/",
        "sec-fetch-site": "cross-site",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "content-type": "application/json",
        "accept": "*/*",
        "authorization": f"Bearer {token}"
    }

def safe_json(r):
    if r.status_code == 567 or "Tencent Cloud EdgeOne" in r.text or "<!doctype html>" in r.text.lower():
        return {
            "_blocked": True,
            "_status": r.status_code,
            "message": f"Blocked by Tencent EdgeOne WAF (HTTP {r.status_code}). Server IP was flagged/rate-limited. Wait 1-2 mins, or run pavo.py locally / set PROXY_URL."
        }
    try:
        return r.json()
    except Exception:
        return {"_raw": r.text[:300], "_status": r.status_code}

video_cache = {}
conversation_images = {}

def check_task_in_history(conv_id, task_id, token):
    url = f"{API_BASE}/api/v1/chat/conversation/history?conversation_id={conv_id}"
    r = req("get", url, headers=get_headers(token), timeout=20)
    data = safe_json(r)
    if data.get("_blocked"):
        return None

    turns = (data.get("data") or {}).get("turns") or []
    if not turns:
        return None

    for turn in reversed(turns):
        asst_msgs = turn.get("assistant") or []
        turn_has_task = any(
            (m.get("data") or {}).get("task_id") == task_id for m in asst_msgs
        )
        for msg in asst_msgs:
            m_type = msg.get("type")
            m_data = msg.get("data") or {}
            if m_type == "GenerationSuccess" and m_data.get("task_id") == task_id:
                results = (m_data.get("data") or {}).get("results") or []
                if results and results[0].get("url"):
                    return {
                        "status": "success",
                        "url": results[0]["url"],
                        "mimetype": results[0].get("mimetype", "video/mp4")
                    }
            elif m_type == "GenerationFailed" and m_data.get("task_id") == task_id:
                err = m_data.get("error_message") or m_data.get("error") or "Queue is full"
                return {"status": "failed", "error": err}
            elif m_type == "PromptSafetyBlocked" and turn_has_task:
                err = m_data.get("error_message") or m_data.get("error") or "Prompt blocked"
                return {"status": "failed", "error": err}
    return None

def monitor_generation(conv_id, task_id, token):
    wait_time = 0
    while wait_time < 1200:
        time.sleep(20)
        wait_time += 20
        try:
            res = check_task_in_history(conv_id, task_id, token)
            if res:
                if task_id in video_cache:
                    video_cache[task_id].update(res)
                return
        except Exception:
            pass

    if task_id in video_cache and video_cache[task_id]["status"] == "queued":
        video_cache[task_id]["status"] = "timeout"

@app.route('/')
def home():
    return f"Pavo Backend Active! (TLS Impersonation: {'Chrome/curl_cffi' if USE_CURL_CFFI else 'standard requests'})"

@app.route('/api/generate', methods=['POST'])
def generate():
    try:
        d = request.json or {}
        token = d.get("token")
        if not token:
            return jsonify({"status": "error", "message": "JWT Token is required"})

        prompt = d.get("prompt", "")
        duration = int(d.get("duration", 12))
        ratio = d.get("ratio", "9:16")
        image_url = d.get("image_url")
        existing_conv_id = d.get("conv_id")
        is_spam = bool(d.get("is_spam", False))

        if existing_conv_id and not is_spam:
            conv_id = existing_conv_id
            if not image_url and conv_id in conversation_images:
                image_url = conversation_images[conv_id]
        else:
            conv_url = f"{API_BASE}/api/v1/chat/conversation"
            title_json = json.dumps([{"type": "text", "content": prompt[:60]}])
            r_conv = req(
                "post",
                conv_url,
                json={"title": title_json, "folder_id": "", "kb_strict": False},
                headers=get_headers(token),
                timeout=20
            )
            conv_data = safe_json(r_conv)
            if conv_data.get("_blocked"):
                return jsonify({"status": "error", "message": conv_data["message"]})
            conv_id = (conv_data.get("data") or {}).get("conversation_id")
            if not conv_id:
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

        r = req(
            "post",
            stream_url,
            json=payload,
            headers={**get_headers(token), "accept": "text/event-stream"},
            stream=True,
            timeout=60
        )
        try:
            if r.status_code == 567:
                return jsonify({"status": "error", "message": "Blocked by Tencent EdgeOne WAF (HTTP 567)."})
            if r.status_code != 200:
                err_bytes = b"".join(r.iter_content())
                err_body = err_bytes.decode("utf-8", errors="ignore")[:300]
                if "EdgeOne" in err_body or "<!doctype html>" in err_body.lower():
                    return jsonify({"status": "error", "message": f"Blocked by Tencent EdgeOne (HTTP {r.status_code})."})
                return jsonify({"status": "error", "message": f"Stream HTTP {r.status_code}: {err_body}"})

            for line in r.iter_lines():
                if not line:
                    continue
                line_str = line.decode('utf-8', errors='ignore') if isinstance(line, bytes) else line
                if line_str.startswith("data:"):
                    try:
                        evt = json.loads(line_str[5:].strip())
                        etype = evt.get("type")
                        if etype == "MessageDelta" and "content" in (evt.get("data") or {}):
                            stream_text = evt["data"]["content"]
                        elif etype == "GenerationStart":
                            task_id = evt.get("task_id")
                            break
                        elif etype in ["GenerationFailed", "PromptSafetyBlocked"]:
                            edata = evt.get("data") or {}
                            err_msg = (
                                edata.get("error_message")
                                or edata.get("error")
                                or evt.get("error_message")
                                or evt.get("error")
                                or "Failed"
                            )
                            return jsonify({"status": "error", "message": err_msg, "text": stream_text, "conv_id": conv_id})
                    except Exception:
                        pass
        finally:
            try:
                r.close()
            except Exception:
                pass

        if not task_id:
            return jsonify({"status": "error", "message": "Failed to start generation stream.", "text": stream_text, "conv_id": conv_id})

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
        r_pre = req(
            "post",
            pre_url,
            json={"purpose": "chat_attachment", "content_type": ctype, "filename": fname},
            headers=get_headers(token),
            timeout=20
        )
        pre_data = safe_json(r_pre)
        if pre_data.get("_blocked"):
            return jsonify({"status": "error", "message": pre_data["message"]})

        pdata = pre_data.get("data") or {}
        if not pdata.get("upload_url"):
            return jsonify({"status": "error", "message": f"Presign failed: {pre_data}"})

        req("put", pdata["upload_url"], data=file.read(), headers={"Content-Type": ctype}, timeout=30)
        req(
            "post",
            f"{API_BASE}/api/v1/file/inspect",
            json={"content_type": ctype, "url": pdata["public_url"]},
            headers=get_headers(token),
            timeout=20
        )
        return jsonify({"status": "success", "url": pdata["public_url"]})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/history', methods=['GET'])
def get_projects():
    try:
        token = request.headers.get("X-Pavo-Token")
        if not token:
            return jsonify({"status": "error", "message": "Token missing in headers"})

        r = req("get", f"{API_BASE}/api/v1/chat/projects?page_size=50&page=1", headers=get_headers(token), timeout=20)
        data = safe_json(r)
        if data.get("_blocked"):
            return jsonify({"status": "error", "message": data["message"]})
        if data.get("code") != "000000":
            return jsonify({"status": "error", "message": data.get("message") or "API Error"})

        return jsonify({"status": "success", "projects": (data.get("data") or {}).get("list") or []})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/videos/<conv_id>', methods=['GET'])
def get_videos(conv_id):
    try:
        token = request.headers.get("X-Pavo-Token")
        if not token:
            return jsonify({"status": "error", "message": "Token missing in headers"})

        r = req(
            "get",
            f"{API_BASE}/api/v1/chat/conversation/history?conversation_id={conv_id}",
            headers=get_headers(token),
            timeout=20
        )
        data = safe_json(r)
        if data.get("_blocked"):
            return jsonify({"status": "error", "message": data["message"]})
        if data.get("code") != "000000":
            return jsonify({"status": "error", "message": data.get("message") or data.get("_raw") or "Failed to load history"})

        conv_data = data.get("data") or {}
        turns = conv_data.get("turns") or []
        is_running = bool(conv_data.get("is_running", False))
        saved_img = conversation_images.get(conv_id)

        items = []
        for idx, turn in enumerate(turns):
            prompt = "Unknown"
            turn_img = saved_img
            for u_msg in (turn.get("user") or []):
                utype = u_msg.get("type")
                udata = u_msg.get("data") or {}
                if utype == "Message":
                    prompt = udata.get("content", prompt)
                elif utype == "File" and udata.get("url"):
                    turn_img = udata["url"]

            text_parts = []
            task_id = None
            media_url = None
            media_mime = "video/mp4"
            error_msg = None

            for a_msg in (turn.get("assistant") or []):
                atype = a_msg.get("type")
                adata = a_msg.get("data") or {}
                if atype == "Message":
                    content = adata.get("content", "")
                    if content:
                        text_parts.append(content)
                elif atype == "GenerationStart":
                    task_id = adata.get("task_id") or task_id
                elif atype == "GenerationSuccess":
                    results = (adata.get("data") or {}).get("results") or []
                    if results and results[0].get("url"):
                        media_url = results[0]["url"]
                        media_mime = results[0].get("mimetype", "video/mp4")
                elif atype in ["GenerationFailed", "PromptSafetyBlocked"]:
                    error_msg = adata.get("error_message") or adata.get("error") or "Generation failed"
                elif atype == "QuotaTryDeduct" and adata.get("deducted") is False and adata.get("insufficient_hint"):
                    error_msg = adata["insufficient_hint"]

            if media_url:
                status = "success"
            elif error_msg:
                status = "failed"
            elif task_id or (is_running and idx == len(turns) - 1):
                status = "processing"
            elif text_parts:
                status = "text"
            else:
                status = "processing" if is_running else "failed"
                if status == "failed":
                    error_msg = "No result recorded for this turn."

            items.append({
                "status": status,
                "task_id": task_id,
                "url": media_url,
                "mimetype": media_mime,
                "prompt": prompt,
                "image_url": turn_img,
                "text": " ".join(text_parts),
                "error": error_msg
            })

        return jsonify({"status": "success", "videos": items, "is_running": is_running})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/delete_project', methods=['POST'])
def delete_project():
    try:
        d = request.json or {}
        token = d.get("token")
        conv_id = d.get("conv_id")

        url = f"{API_BASE}/api/v1/chat/projects?id={conv_id}&type=ai_creation"
        r = req("delete", url, headers=get_headers(token), timeout=20)
        data = safe_json(r)
        if data.get("_blocked"):
            return jsonify({"status": "error", "message": data["message"]})

        if data.get("code") == "000000":
            return jsonify({"status": "success"})
        else:
            return jsonify({"status": "error", "message": data.get("message", "Unknown error")})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
