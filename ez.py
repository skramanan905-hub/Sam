import telebot
import uuid
import hashlib
import base64
import time
import random
import string
from curl_cffi import requests as curl_requests

# ⚠️ REVOKE THIS TOKEN ON BOTFATHER AND PUT YOUR NEW ONE HERE
BOT_TOKEN = "8713547959:AAGgPZUzgS36zkxyZn83bUJxz0OOpCnycvg"
BASE_URL = "https://raphael.app"

bot = telebot.TeleBot(BOT_TOKEN)

# State dictionary to store user data (waiting for prompt)
user_data = {}

def generate_random_string(length=20):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def get_fresh_session():
    session = curl_requests.Session()
    
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
        timeout=10,
        impersonate="chrome" 
    )
    
    return session

# Helper function to safely edit messages without crashing
def safe_edit(chat_id, message_id, text):
    try:
        bot.edit_message_text(text, chat_id, message_id)
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" in str(e):
            pass # Ignore if text is exactly the same
        else:
            print(f"Telegram Edit Error: {e}")

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "👋 Send me an image first. After uploading, I will ask you for a prompt!")

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    chat_id = message.chat.id
    
    # 1. Download image from Telegram
    file_id = message.photo[-1].file_id
    file_info = bot.get_file(file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    
    # 2. Check if they added a caption.
    if message.caption:
        prompt = message.caption
        process_generation(chat_id, downloaded_file, prompt)
    else:
        user_data[chat_id] = {"image": downloaded_file}
        bot.reply_to(message, "📸 Image received! Now, please send me the prompt (e.g., 'Make the water ripple').")

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
    msg = bot.send_message(chat_id, "🔄 Generating new identity (Bypassing limit)...")
    
    try:
        session = get_fresh_session()
        
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
            "file": {"size": file_size, "type": "image/jpeg", "checksumSHA256": checksum_base64}
        }
        
        safe_edit(chat_id, msg.message_id, "☁️ Preparing upload...")
        r = session.post(f"{BASE_URL}/api/video/upload-input", json=payload, timeout=15, impersonate="chrome")
        data = r.json()
        
        if "uploadUrl" not in data:
            safe_edit(chat_id, msg.message_id, f"❌ Upload prepare failed: {data}")
            return
            
        # 2. Upload to R2
        safe_edit(chat_id, msg.message_id, "📤 Uploading image to server...")
        session.put(data["uploadUrl"], data=image_bytes, headers=data["headers"], timeout=30, impersonate="chrome")
        
        # 3. Confirm Upload
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
        
        if "url" not in img_data:
            safe_edit(chat_id, msg.message_id, f"❌ Confirm failed: {img_data}")
            return
            
        # 4. Ticket
        safe_edit(chat_id, msg.message_id, "🎟️ Requesting generation ticket...")
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
        
        ticket = ticket_data.get("data", {}).get("ticket")
        if not ticket:
            safe_edit(chat_id, msg.message_id, f"❌ Limit Reached or Server Error:\n{ticket_data}")
            return
            
        wait_sec = ticket_data.get("data", {}).get("wait_ms", 80000) / 1000
        
        # 5. Wait
        for remaining in range(int(wait_sec), 0, -5):
            safe_edit(chat_id, msg.message_id, f"⏳ In queue: waiting {remaining}s...")
            time.sleep(5)
            
        # 6. Redeem
        safe_edit(chat_id, msg.message_id, "🎫 Redeeming ticket...")
        r = session.post(f"{BASE_URL}/api/video/anon/redeem", json={"ticket": ticket}, timeout=15, impersonate="chrome")
        
        while r.status_code == 409:
            wait_ms = r.json().get("data", {}).get("wait_ms", 15000)
            safe_edit(chat_id, msg.message_id, f"⏳ Server busy. Waiting {int(wait_ms/1000)}s...")
            time.sleep(wait_ms / 1000)
            r = session.post(f"{BASE_URL}/api/video/anon/redeem", json={"ticket": ticket}, timeout=15, impersonate="chrome")
            
        redeem_data = r.json()
        job_id = redeem_data.get("data", {}).get("job_id")
        
        if not job_id:
            safe_edit(chat_id, msg.message_id, "❌ Redeem failed.")
            return
            
        # 7. Poll
        safe_edit(chat_id, msg.message_id, "🎬 Rendering video (This takes a minute)...")
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
                    bot.delete_message(chat_id, msg.message_id)
                    bot.send_video(chat_id, video_url, caption=f"✅ Done!\nPrompt: {prompt}")
                    return
            elif status == "failed":
                safe_edit(chat_id, msg.message_id, "❌ Rendering failed.")
                return
                
            if progress != last_progress:
                safe_edit(chat_id, msg.message_id, f"🎬 Rendering: {progress}%")
                last_progress = progress
                
            time.sleep(3)
            
    except Exception as e:
        safe_edit(chat_id, msg.message_id, f"Error: {str(e)}")

print("Bot is running...")
bot.infinity_polling()
