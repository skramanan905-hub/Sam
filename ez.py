import os
import time
import random
import threading
from flask import Flask, request, jsonify
from flask_cors import CORS

try:
    from curl_cffi import requests as http_client
    USE_CURL_CFFI = True
except ImportError:
    import requests as http_client
    USE_CURL_CFFI = False

app = Flask(__name__)
CORS(app)

API_BASE = os.environ.get("API_BASE", "https://api.ezmaker.ai").rstrip("/")
PROXY_URL = os.environ.get("PROXY_URL", "").strip()
PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None

FN_NAME = os.environ.get("FN_NAME", "demo-ai-video-generator")
SCENE = os.environ.get("SCENE", "ezmaker-v1")
ORIGIN_FROM = os.environ.get("ORIGIN_FROM", "eb2720d2be87a1f0")
THEME_VERSION = os.environ.get(
    "THEME_VERSION",
    "83EmcUoQTUv50LhNx0VrdcK8rcGexcP35FcZDcpgWsAXEyO4xqL5shCY6sFIWB2Q",
)

# Optional tokens/fingerprints from env if required by upstream
STATIC_FP = os.environ.get("UPSTREAM_FP", "").strip()
STATIC_FP1 = os.environ.get("UPSTREAM_FP1", "").strip()
STATIC_X_GUIDE = os.environ.get("UPSTREAM_X_GUIDE", "").strip()

BROWSER_PROFILES = [
    {
        "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Mobile Safari/537.36",
        "sec-ch-ua": '"Chromium";v="154", "Google Chrome";v="154", "Not A(Brand";v="99"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "accept-language": "en-GB,en;q=0.9,ta-IN;q=0.8,ta;q=0.7,en-US;q=0.6",
    },
    {
        "user-agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Mobile Safari/537.36",
        "sec-ch-ua": '"Chromium";v="145", "Google Chrome";v="145", "Not A(Brand";v="24"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "accept-language": "en-US,en;q=0.9,ta-IN;q=0.8,ta;q=0.7",
    },
    {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Chromium";v="146", "Google Chrome";v="146", "Not A(Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "accept-language": "en-US,en;q=0.9",
    },
]

task_cache = {}


def req(method, url, **kwargs):
    if USE_CURL_CFFI:
        kwargs.setdefault("impersonate", "chrome")
    if PROXIES:
        kwargs.setdefault("proxies", PROXIES)
    return getattr(http_client, method)(url, **kwargs)


def pick_profile(profile_index=None):
    if profile_index is not None:
        idx = int(profile_index) % len(BROWSER_PROFILES)
    else:
        idx = random.randrange(len(BROWSER_PROFILES))
    return idx, BROWSER_PROFILES[idx]


def get_headers(profile=None, is_json=True):
    _, prof = pick_profile(0 if profile is None else None) if isinstance(profile, int) else (0, profile or BROWSER_PROFILES[0])
    headers = {
        "accept": "application/json, text/plain, */*",
        "origin": "https://ezmaker.ai",
        "referer": "https://ezmaker.ai/",
        "sec-fetch-site": "same-site",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
        "accept-encoding": "gzip, deflate, br",
        "user-agent": prof["user-agent"],
        "sec-ch-ua": prof["sec-ch-ua"],
        "sec-ch-ua-mobile": prof["sec-ch-ua-mobile"],
        "sec-ch-ua-platform": prof["sec-ch-ua-platform"],
        "accept-language": prof["accept-language"],
        "x-code": str(int(time.time() * 1000)),
        "nonce": FN_NAME,
        "theme-version": THEME_VERSION,
    }
    if is_json:
        headers["content-type"] = "application/json"
    if STATIC_FP:
        headers["fp"] = STATIC_FP
    if STATIC_FP1:
        headers["fp1"] = STATIC_FP1
    if STATIC_X_GUIDE:
        headers["x-guide"] = STATIC_X_GUIDE
    return headers


def poll_once(task_id, profile_index=0):
    _, prof = pick_profile(profile_index)
    url = f"{API_BASE}/api/v1/aikit/check-status"
    payload = {
        "task_id": task_id,
        "fn_name": FN_NAME,
        "call_type": 2,
        "consume_type": -1,
        "request_from": 37,
        "origin_from": ORIGIN_FROM,
    }
    r = req("post", url, json=payload, headers=get_headers(prof, is_json=True), timeout=25)
    raw = r.json()
    inner = raw.get("data") or {}
    status_code = inner.get("status")
    video_url = inner.get("result_image")
    err = inner.get("error") or ""

    if status_code == 2 and video_url:
        return {"status": "success", "url": video_url, "raw": raw}
    if err:
        return {"status": "failed", "error": err, "raw": raw}
    return {"status": "queued", "raw": raw}


def monitor_task(task_id, profile_index=0):
    waited = 0
    while waited < 600:
        time.sleep(5)
        waited += 5
        try:
            res = poll_once(task_id, profile_index=profile_index)
            if res["status"] in ("success", "failed"):
                task_cache[task_id] = {**(task_cache.get(task_id) or {}), **res}
                return
        except Exception:
            pass
    if task_id in task_cache and task_cache[task_id].get("status") == "queued":
        task_cache[task_id]["status"] = "timeout"


@app.route("/")
def home():
    return jsonify({
        "status": "ok",
        "tls_impersonation": USE_CURL_CFFI,
        "profiles": len(BROWSER_PROFILES),
    })


@app.route("/api/upload", methods=["POST"])
def upload_image():
    try:
        if "image" not in request.files and "file" not in request.files:
            return jsonify({"status": "error", "message": "No image file provided"}), 400
        f = request.files.get("image") or request.files.get("file")
        _, prof = pick_profile(request.form.get("profile_index"))
        headers = get_headers(prof, is_json=False)
        files = {"file": (f.filename or "upload.jpg", f.read(), f.mimetype or "image/jpeg")}
        r = req("post", f"{API_BASE}/api/v1/aikit/upload-oss-file", files=files, headers=headers, timeout=45)
        data = r.json()
        return jsonify({"status": "success", "upstream": data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/generate", methods=["POST"])
def generate():
    try:
        d = request.json or {}
        prompt = (d.get("prompt") or "").strip()
        source_image = (d.get("source_image") or d.get("image_url") or "").strip()
        if not prompt or not source_image:
            return jsonify({"status": "error", "message": "prompt and source_image are required"}), 400

        duration = int(d.get("duration", 4))
        resolution = d.get("resolution", "540p")
        scene = d.get("scene", SCENE)
        idx, prof = pick_profile(d.get("profile_index"))

        payload = {
            "fn_name": FN_NAME,
            "call_type": 2,
            "input": {
                "scene": scene,
                "prompt": prompt,
                "duration": duration,
                "resolution": resolution,
                "source_image": source_image,
            },
            "request_from": 37,
            "origin_from": ORIGIN_FROM,
        }

        r = req(
            "post",
            f"{API_BASE}/api/v1/aikit/create",
            json=payload,
            headers=get_headers(prof, is_json=True),
            timeout=30,
        )
        data = r.json()
        task_id = (data.get("data") or {}).get("task_id")
        if not task_id:
            return jsonify({"status": "error", "message": "No task_id returned", "upstream": data}), 400

        task_cache[task_id] = {"status": "queued", "profile_index": idx}
        threading.Thread(target=monitor_task, args=(task_id, idx), daemon=True).start()

        return jsonify({
            "status": "success",
            "task_id": task_id,
            "profile_index": idx,
            "upstream": data,
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/status/<task_id>", methods=["GET"])
def status(task_id):
    cached = task_cache.get(task_id)
    if cached and cached.get("status") != "queued":
        return jsonify(cached)

    prof_idx = request.args.get("profile_index", type=int)
    if prof_idx is None and cached:
        prof_idx = cached.get("profile_index", 0)

    try:
        res = poll_once(task_id, profile_index=prof_idx or 0)
        if res["status"] != "queued":
            task_cache[task_id] = {**(cached or {}), **res}
        return jsonify({**(cached or {}), **res, "task_id": task_id})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
