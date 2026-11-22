import telebot
import uuid
import time
import json
import base64
from curl_cffi import requests as curl_requests

# ⚠️ PUT YOUR NEW BOT TOKEN HERE
BOT_TOKEN = "8890014279:AAGuKNVfg2WJ21DXCS_kBXgVlexjRxXUhL8"
BASE_URL = "https://magichour.ai"

bot = telebot.TeleBot(BOT_TOKEN)
user_data = {}

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

    # Fake Device ID to reset the limit
    fake_distinct_id = str(uuid.uuid4())
    fake_created_at = int(time.time() * 1000)
    fake_mh_did = base64.b64encode(json.dumps({
        "distinct_id": fake_distinct_id,
        "created_at": fake_created_at
    }).encode()).decode()
    session.cookies.set("mh_did", fake_mh_did)
    
    # Get CSRF token
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
        
        # CRITICAL FIX: Generate ONE task_id and use it for EVERYTHING
        task_id = str(uuid.uuid4())
        
        # --- STEP 1: Get Resumable Upload URL ---
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
        
        if r.status_code != 200:
            safe_edit(chat_id, msg.message_id, f"❌ Step 1 Failed: {r.text[:200]}")
            return
            
        upload_data = r.json().get("json", {})
        upload_url = upload_data.get("uploadUrl")
        file_path = upload_data.get("filePath")
        
        if not upload_url or not file_path:
            safe_edit(chat_id, msg.message_id, "❌ No upload URL returned.")
            return
            
        # --- STEP 2: Upload Image to GCS ---
        safe_edit(chat_id, msg.message_id, "📤 Step 2: Uploading image...")
        
        file_size = len(image_bytes)
        headers = {
            "Content-Type": "image/jpeg",
            "Content-Length": str(file_size),
            "Content-Range": f"bytes 0-{file_size-1}/{file_size}"
        }
        
        put_res = session.put(upload_url, data=image_bytes, headers=headers, impersonate="chrome")
        
        if put_res.status_code not in [200, 201]:
            safe_edit(chat_id, msg.message_id, f"❌ Upload failed.\nStatus: {put_res.status_code}")
            return
            
        # --- STEP 3: Start the Video Generation Job ---
        safe_edit(chat_id, msg.message_id, "🎟️ Step 3: Starting generation...")
        
        payload = {
            "prompt": prompt,
            "image_file_path": file_path, 
            "aspect_ratio": "9:16",
            "model": "any-to-video-v5",
            "duration": 5,
            "client_request_id": task_id  # Same ID here
        }
        
        r = session.post(f"{BASE_URL}/api/free-tools/v5/any-to-video", json=payload, impersonate="chrome")
        
        if r.status_code == 429:
            safe_edit(chat_id, msg.message_id, "❌ Limit Reached! Turn on Airplane mode.")
            return
        elif r.status_code != 200:
            safe_edit(chat_id, msg.message_id, f"❌ Generation failed: {r.text[:200]}")
            return
            
        # --- STEP 4: Poll for the Result ---
        start_time = time.time()
        
        while True:
            # Same ID here too
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
                bot.send_video(chat_id, video_url, caption=f"✅ Done in {timer_str}!\nPrompt: {prompt}")
                return
            elif status == "FAILED":
                safe_edit(chat_id, msg.message_id, f"❌ Rendering failed after {timer_str}.")
                return
                
            raw_status = json.dumps(job_data, indent=2)
            msg_text = f"⏳ Rendering... ({timer_str})\nQueue: {position}\n```json\n{raw_status[:400]}\n```"
            safe_edit(chat_id, msg.message_id, msg_text, parse_mode="Markdown")
                
            time.sleep(4)
            
    except Exception as e:
        safe_edit(chat_id, msg.message_id, f"Error: {str(e)}")

print("Magic Hour Bot is running...")
bot.infinity_polling()
