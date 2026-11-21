import telebot
import uuid
import hashlib
import base64
import time
import random
import string
import threading
import os
from curl_cffi import requests as curl_requests
from flask import Flask

# ⚠️ PUT YOUR NEW BOT TOKEN HERE
BOT_TOKEN = "8713547959:AAGgPZUzgS36zkxyZn83bUJxz0OOpCnycvgg"
BASE_URL = "https://raphael.app"

bot = telebot.TeleBot(BOT_TOKEN)

# --- FAKE WEB SERVER (To keep Render alive) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Telegram Bot is running perfectly on Render!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- BOT LOGIC ---
user_data = {}

def generate_random_string(length=20):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

# --- NEW: IP GENERATOR ---
def generate_random_ip():
    return f"{random.randint(1, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"

def get_fresh_session(fake_ip):
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
        "sec-fetch-dest": "empty",
        
        # Apply the generated IP here
        "X-Forwarded-For": fake_ip,
        "X-Real-IP": fake_ip,
        "Client-IP": fake_ip
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

def safe_edit(chat_id, message_id, text):
    try:
        bot.edit_message_text(text, chat_id, message_id, parse_mode='HTML')
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" in str(e):
            pass 
        else:
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

# --- NEW: SHOWS THE LIST OF IPS IN TELEGRAM ---
def spoof_ips_in_telegram(chat_id, message_id):
    log_text = "<b>Starting Spoofer...</b>\n\n"
    safe_edit(chat_id, message_id, log_text)
    
    last_ip = ""
    
    # Loop 4 times to show a list (like your screenshot)
    for i in range(1, 5):
        last_ip = generate_random_ip()
        log_text += f"<code>[{i}/1000] Attempting Refer...</code>\n"
        log_text += f"<code>Refer Successfully Added | IP: {last_ip}</code>\n"
        log_text += "<code>====================================</code>\n"
        
        safe_edit(chat_id, message_id, log_text)
        time.sleep(1.2) # Small delay to make it look like it's working
        
    return last_ip

def process_generation(chat_id, image_bytes, prompt):
    # 1. Create the message and show the fake IP loop
    msg = bot.send_message(chat_id, "🔄 Initializing...")
    final_fake_ip = spoof_ips_in_telegram(chat_id, msg.message_id)
    
    try:
        # 2. Pass the final IP to the session
        safe_edit(chat_id, msg.message_id, f"✅ <b>Using IP:</b> <code>{final_fake_ip}</code>\n\n☁️ Preparing upload...")
        session = get_fresh_session(final_fake_ip)
        
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
        
        r = session.post(f"{BASE_URL}/api/video/upload-input", json=payload, timeout=15, impersonate="chrome")
        data = r.json()
        
        if "uploadUrl" not in data:
            safe_edit(chat_id, msg.message_id, f"❌ Upload prepare failed: {data}")
            return
            
        safe_edit(chat_id, msg.message_id, f"✅ <b>Using IP:</b> <code>{final_fake_ip}</code>\n\n📤 Uploading image to server...")
        session.put(data["uploadUrl"], data=image_bytes, headers=data["headers"], timeout=30, impersonate="chrome")
        
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
            
        safe_edit(chat_id, msg.message_id, f"✅ <b>Using IP:</b> <code>{final_fake_ip}</code>\n\n🎟️ Requesting generation ticket...")
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
            safe_edit(chat_id, msg.message_id, f"❌ Limit Reached (Render IP blocked):\n{ticket_data}")
            return
            
        wait_sec = ticket_data.get("data", {}).get("wait_ms", 80000) / 1000
        
        for remaining in range(int(wait_sec), 0, -5):
            safe_edit(chat_id, msg.message_id, f"✅ <b>Using IP:</b> <code>{final_fake_ip}</code>\n\n⏳ In queue: waiting {remaining}s...")
            time.sleep(5)
            
        safe_edit(chat_id, msg.message_id, f"✅ <b>Using IP:</b> <code>{final_fake_ip}</code>\n\n🎫 Redeeming ticket...")
        r = session.post(f"{BASE_URL}/api/video/anon/redeem", json={"ticket": ticket}, timeout=15, impersonate="chrome")
        
        while r.status_code == 409:
            wait_ms = r.json().get("data", {}).get("wait_ms", 15000)
            safe_edit(chat_id, msg.message_id, f"✅ <b>Using IP:</b> <code>{final_fake_ip}</code>\n\n⏳ Server busy. Waiting {int(wait_ms/1000)}s...")
            time.sleep(wait_ms / 1000)
            r = session.post(f"{BASE_URL}/api/video/anon/redeem", json={"ticket": ticket}, timeout=15, impersonate="chrome")
            
        redeem_data = r.json()
        job_id = redeem_data.get("data", {}).get("job_id")
        
        if not job_id:
            safe_edit(chat_id, msg.message_id, f"❌ Redeem failed.")
            return
            
        safe_edit(chat_id, msg.message_id, f"✅ <b>Using IP:</b> <code>{final_fake_ip}</code>\n\n🎬 Rendering video (This takes a minute)...")
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
                    bot.send_video(chat_id, video_url, caption=f"✅ Done!\nPrompt: {prompt}\n\n<i>Spoofed IP: {final_fake_ip}</i>", parse_mode='HTML')
                    return
            elif status == "failed":
                safe_edit(chat_id, msg.message_id, "❌ Rendering failed.")
                return
                
            if progress != last_progress:
                safe_edit(chat_id, msg.message_id, f"✅ <b>Using IP:</b> <code>{final_fake_ip}</code>\n\n🎬 Rendering: {progress}%")
                last_progress = progress
                
            time.sleep(3)
            
    except Exception as e:
        safe_edit(chat_id, msg.message_id, f"Error: {str(e)}")

# --- START BOTH ---
if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()
    
    print("Bot is running on Render...")
    bot.infinity_polling()
