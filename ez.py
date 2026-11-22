import telebot
import uuid
import time
import json
import base64
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from curl_cffi import requests as curl_requests

BOT_TOKEN = "8890014279:AAGuKNVfg2WJ21DXCS_kBXgVlexjRxXUhL8"
BASE_URL = "https://magichour.ai"

bot = telebot.TeleBot(BOT_TOKEN)
user_data = {}

# --- RENDER PORT BINDING FIX ---
def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is running!")
    server = HTTPServer(('0.0.0.0', port), Handler)
    server.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()
# -------------------------------

def get_fresh_session():
    session = curl_requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Linux; Android 15; I2301 Build/AP3A.240905.015.A2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.8103.50 Mobile Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/products/ai-video-generator",
        "x-requested-with": "mark.via.gp",
        "x-timezone-offset": "-330",
        "sec-ch-ua": '"Not-A.Brand";v="99", "Android WebView";v="157", "Chromium";v="157"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty"
    })

    fake_distinct_id = str(uuid.uuid4())
    fake_created_at = int(time.time() * 1000)
    fake_mh_did = base64.b64encode(json.dumps({
        "distinct_id": fake_distinct_id,
        "created_at": fake_created_at
    }).encode()).decode()
    session.cookies.set("mh_did", fake_mh_did)
    
    session.get(f"{BASE_URL}/api/auth/csrf", impersonate="chrome")
    return session

def safe_edit(chat_id, message_id, text, parse_mode=None):
    try:
        if parse_mode:
            bot.edit_message_text(text, chat_id, message_id, parse_mode=parse_mode)
        else:
            bot.edit_message_text(text, chat_id, message_id)
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" not in str(e):
            print(f"Telegram Edit Error: {e}")

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "👋 Send me an image first. After uploading, I will ask you for a prompt!")

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    chat_id = message.chat.id
    file_id = message.photo[-1].file_id
    file_info = bot.get_file(file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    
    if message.caption:
        prompt = message.caption
        process_generation(chat_id, downloaded_file, prompt)
    else:
        user_data[chat_id] = {"image": downloaded_file}
        bot.reply_to(message, "📸 Image received! Now, please send me the prompt.")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    chat_id = message.chat.id
    prompt = message.text
    
    if chat_id in user_data and "image" in user_data[chat_id]:
        image_bytes = user_data[chat_id]["image"]
        del user_data[chat_id]
        process_generation(chat_id, image_bytes, prompt)
    else:
        bot.reply_to(message, "Please send an image first, then type your prompt.")

def process_generation(chat_id, image_bytes, prompt):
    msg = bot.send_message(chat_id, "🔄 Starting process...")
    
    try:
        session = get_fresh_session()
        task_id = str(uuid.uuid4())
        
        safe_edit(chat_id, msg.message_id, "☁️ Step 1: Requesting upload slot...")
        
        upload_req_payload = {
            "json": {
                "assetPrefix": "image-to-video",
                "taskId": task_id,
                "fileName": "source.jpg",
                "fileType": "image/jpeg",
                "filePrefix": "source",
                "includeReadUrl": False
            }
        }
        
        r = session.post(f"{BASE_URL}/rpc/freeToolUpload/getResumableUploadUrl", json=upload_req_payload, impersonate="chrome")
        
        raw_res1 = json.dumps(r.json(), indent=2)
        safe_edit(chat_id, msg.message_id, f"☁️ Step 1 Response:\n```json\n{raw_res1[:800]}\n```", parse_mode="Markdown")
        time.sleep(1)
        
        if r.status_code != 200:
            return
            
        upload_data = r.json().get("json", {})
        upload_url = upload_data.get("uploadUrl")
        file_path = upload_data.get("filePath")
        
        if not upload_url or not file_path:
            safe_edit(chat_id, msg.message_id, "❌ Bad upload response.")
            return
            
        safe_edit(chat_id, msg.message_id, "📤 Step 2: Uploading image to Google Cloud...")
        
        file_size = len(image_bytes)
        
        headers = {
            "Content-Type": "image/jpeg",
            "Content-Length": str(file_size),
            "Content-Range": f"bytes 0-{file_size-1}/{file_size}"
        }
        
        put_res = session.put(upload_url, data=image_bytes, headers=headers, impersonate="chrome")
        
        if put_res.status_code not in [200, 201]:
            safe_edit(chat_id, msg.message_id, f"❌ Upload failed.\nStatus: {put_res.status_code}\n{put_res.text[:200]}")
            return
            
        safe_edit(chat_id, msg.message_id, "🎟️ Step 3: Starting video generation...")
        
        payload = {
            "prompt": prompt,
            "image_file_path": file_path,
            "aspect_ratio": "9:16",
            "model": "any-to-video-v5",
            "duration": 5,
            "client_request_id": task_id
        }
        
        r = session.post(f"{BASE_URL}/api/free-tools/v5/any-to-video", json=payload, impersonate="chrome")
        
        raw_res2 = json.dumps(r.json(), indent=2)
        safe_edit(chat_id, msg.message_id, f"🎟️ Step 3 Response:\n```json\n{raw_res2[:800]}\n```", parse_mode="Markdown")
        time.sleep(2)
        
        if r.status_code == 429:
            safe_edit(chat_id, msg.message_id, "❌ Limit Reached! Turn on Airplane mode for 5 seconds and try again.")
            return
        elif r.status_code != 200:
            return
            
        start_time = time.time()
        
        while True:
            r = session.get(f"{BASE_URL}/api/free-tools/v5/any-to-video/{task_id}/status", impersonate="chrome")
            job_data = r.json()
            status = job_data.get("status")
            position = job_data.get("position", "?")
            
            elapsed = int(time.time() - start_time)
            mins, secs = divmod(elapsed, 60)
            timer_str = f"{mins}m {secs}s"
            
            if status == "SUCCESS":
                video_url = job_data["files"][0]["url"]
                bot.delete_message(chat_id, msg.message_id)
                bot.send_video(chat_id, video_url, caption=f"✅ Done in {timer_str}!\nPrompt: {prompt}\nRemaining: {job_data.get('remaining')}")
                return
            elif status == "FAILED":
                safe_edit(chat_id, msg.message_id, f"❌ Rendering failed after {timer_str}.")
                return
                
            raw_status = json.dumps(job_data, indent=2)
            msg_text = f"⏳ Rendering... ({timer_str})\nQueue Pos: {position}\n```json\n{raw_status[:500]}\n```"
            safe_edit(chat_id, msg.message_id, msg_text, parse_mode="Markdown")
                
            time.sleep(4)
            
    except Exception as e:
        safe_edit(chat_id, msg.message_id, f"Error: {str(e)}")

print("Magic Hour Bot is running...")
bot.infinity_polling()
