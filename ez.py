import os
import time
import json
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

API_BASE = "https://api.ezmaker.ai"
FP = "805c38b05d5067353f9ee01049e16e68"
THEME_VER = "83EmcUoQTUv50LhNx0VrdcK8rcGexcP35FcZDcpgWsAXEyO4xqL5shCY6sFIWB2Q"
ORIGIN_FROM = "eb2720d2be87a1f0"
REQUEST_FROM = 37
FN_NAME = "demo-ai-video-generator"

CAPTURED_FP1 = "PN4BmzV7ykaJvkI+67tZ/ZnE2izDNMkD9Hjej/DrrMykw5ib+PUQ7twUtwLogAzK"
CAPTURED_GUIDE = "GdfsSukh9eXq2DnWPACJ+6U3/A8DcLtQRuwzbTc8VLW8gRwPAn6MT3Q4LnRwojUNNr2z57cAp/w6HATro8t8PiOVPtVAnS6Vvvv6GiD4QuWk+C/mUK70QFigEBJ91os6aSRd2oilRh0w2M6bAPkDl5iAdKh48Bz0Rdgw5wmfB0s="

def req(method, url, **kwargs):
    if USE_CURL_CFFI:
        kwargs.setdefault("impersonate", "chrome")
    return getattr(http_client, method)(url, **kwargs)

def get_headers():
    return {
        "sec-ch-ua-platform": "\"Android\"",
        "x-code": str(int(time.time() * 1000)),
        "sec-ch-ua": "\"Chromium\";v=\"154\", \"Google Chrome\";v=\"154\", \"Not A(Brand\";v=\"99\"",
        "fp1": CAPTURED_FP1,
        "sec-ch-ua-mobile": "?1",
        "nonce": FN_NAME,
        "theme-version": THEME_VER,
        "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Mobile Safari/537.36",
        "accept": "application/json, text/plain, */*",
        "fp": FP,
        "content-type": "application/json",
        "origin": "https://ezmaker.ai",
        "x-guide": CAPTURED_GUIDE,
        "sec-fetch-site": "same-site",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
        "referer": "https://ezmaker.ai/",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en-GB,en;q=0.9,ta-IN;q=0.8,ta;q=0.7,en-US;q=0.6,zh-CN;q=0.5,zh;q=0.4"
    }

@app.route('/')
def home():
    return "EzMaker Backend Active!"

@app.route('/api/generate', methods=['POST'])
def generate():
    try:
        d = request.json or {}
        prompt = d.get("prompt", "")
        duration = int(d.get("duration", 4))
        resolution = d.get("resolution", "540p")
        source_image = d.get("source_image")

        inp = {
            "scene": "ezmaker-v1",
            "prompt": prompt,
            "duration": duration,
            "resolution": resolution
        }
        if source_image:
            inp["source_image"] = source_image

        body = {
            "fn_name": FN_NAME,
            "call_type": 2,
            "input": inp,
            "request_from": REQUEST_FROM,
            "origin_from": ORIGIN_FROM
        }

        r = req("post", f"{API_BASE}/api/v1/aikit/create", json=body, headers=get_headers(), timeout=30)
        data = r.json()
        
        # EzMaker returns task_id inside data
        task_id = data.get("data", {}).get("task_id")
        
        if not task_id:
            return jsonify({"status": "error", "message": f"EzMaker API Error: {data}"})
            
        return jsonify({"status": "success", "task_id": task_id, "raw": data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/status/<task_id>', methods=['GET'])
def check_status(task_id):
    try:
        body = {
            "task_id": task_id,
            "fn_name": FN_NAME,
            "call_type": 2,
            "consume_type": -1,
            "request_from": REQUEST_FROM,
            "origin_from": ORIGIN_FROM
        }
        r = req("post", f"{API_BASE}/api/v1/aikit/check-status", json=body, headers=get_headers(), timeout=20)
        data = r.json()
        
        status_val = data.get("data", {}).get("status")
        if status_val == 2:
            return jsonify({
                "status": "success", 
                "url": data.get("data", {}).get("result_image"),
                "mimetype": "video/mp4"
            })
        elif status_val in [3, 4, -1]:
            return jsonify({"status": "failed", "error": data.get("data", {}).get("error", "Generation failed")})
        else:
            return jsonify({"status": "processing", "raw": data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/upload', methods=['POST'])
def upload():
    try:
        if 'image' not in request.files:
            return jsonify({"status": "error", "message": "No file sent from frontend"})
            
        f = request.files['image']
        # Use exact content type, fallback to jpeg
        ctype = f.content_type if f.content_type in ("image/jpeg", "image/png", "image/webp") else "image/jpeg"
        
        files = {"file": (f.filename or "upload.jpg", f.read(), ctype)}
        h = get_headers()
        h.pop("content-type", None) # Let requests set multipart boundary
        
        r = req("post", f"{API_BASE}/api/v1/aikit/upload-oss-file", files=files, headers=h, timeout=60)
        data = r.json()
        
        # SMART EXTRACTOR: Try all known possible keys for the URL
        url = None
        if "data" in data:
            if isinstance(data["data"], dict):
                url = data["data"].get("url") or data["data"].get("file_url") or data["data"].get("source_image")
            elif isinstance(data["data"], str):
                url = data["data"]
                
        if not url:
            # If we can't find the URL, send the raw JSON back to the frontend so you can see it
            return jsonify({"status": "error", "message": f"Could not find URL in response: {data}"})

        return jsonify({"status": "success", "url": url})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
