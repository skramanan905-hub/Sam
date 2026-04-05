import telebot
import requests
import base64
import json
import os
import time
import queue
import threading

# ================= CONFIGURATION =================
API_TOKEN = "8748542024:AAHbhNJHZP8Tdo_OLam-h6CJGMG9S5n6MDU"
bot = telebot.TeleBot(API_TOKEN)

# Live3D API Endpoints
VERIFY_URL = "https://api.live3d.io/api/v1/verify_token"
TAGGER_URL = "https://api.live3d.io/api/v1/generation/img2prompt"

# Task Queue System
task_queue = queue.Queue()
SESSION_FILE = "live3d_sessions.json"

# --- SESSION HELPERS ---
def load_token(uid):
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, "r") as f:
            return json.load(f).get(str(uid))
    return None

def save_token(uid, token):
    data = {}
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, "r") as f:
            data = json.load(f)
    data[str(uid)] = token
    with open(SESSION_FILE, "w") as f:
        json.dump(data, f, indent=4)

# --- THE BACKGROUND WORKER (One-by-One Logic) ---
def worker():
    while True:
        # Get next task from the "Waiting Line"
        task = task_queue.get()
        if task is None: break
        
        chat_id, file_id, status_msg_id, token = task
        
        try:
            # 1. Download image from Telegram
            file_info = bot.get_file(file_id)
            img_content = bot.download_file(file_info.file_path)
            
            # 2. Convert to Base64 format from your data
            encoded = base64.b64encode(img_content).decode('utf-8')
            base64_payload = f"data:image/webp;base64,{encoded}"

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Origin": "https://animegenius.live3d.io",
                "Referer": "https://animegenius.live3d.io/"
            }
            
            payload = {"image": base64_payload, "consume_points": 1}

            # 3. Send Request and Check Response
            res = requests.post(TAGGER_URL, headers=headers, json=payload)
            
            # Anti-Crash: Check if response is valid JSON
            if res.status_code == 200:
                tag_data = res.json()
                prompt = tag_data.get('data', 'No tags returned.')
                
                # Fetch Points
                b_res = requests.post(VERIFY_URL, headers=headers, json={})
                points = b_res.json().get('points', '??')

                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_msg_id,
                    text=f"📝 **Prompt Generated:**\n`{prompt}`\n\n💰 **Remaining:** `{points}` Points",
                    parse_mode="Markdown"
                )
            elif res.status_code == 429:
                bot.edit_message_text(f"⚠️ **Rate Limited:** Server is busy. Retrying in 10s...", chat_id, status_msg_id)
                time.sleep(10)
                task_queue.put(task) # Put back in line to try again
            else:
                bot.edit_message_text(f"❌ **API Error ({res.status_code}):** Check token or image size.", chat_id, status_msg_id)

        except Exception as e:
            bot.edit_message_text(f"🧨 **Worker Error:** {str(e)}", chat_id, status_msg_id)
        
        # 4. Mandatory Safety Sleep (The Pacing)
        # This prevents sending 50 requests at once to the API
        time.sleep(2.5) 
        task_queue.task_done()

# Start the background thread
threading.Thread(target=worker, daemon=True).start()

# --- BOT COMMANDS ---
@bot.message_handler(commands=['start'])
def start(m):
    bot.reply_to(m, "🤖 **AnimeGenius Sequential Bot**\n\nUse `/login YOUR_TOKEN` first.\nThen send images (one or many). I will process them one-by-one.")

@bot.message_handler(commands=['login'])
def login(m):
    args = m.text.split()
    if len(args) < 2: return bot.reply_to(m, "❌ Use: `/login token`")
    token = args[1].replace("Bearer ", "").strip()
    
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        res = requests.post(VERIFY_URL, headers=headers, json={})
        if res.status_code == 200:
            save_token(m.chat.id, token)
            bot.reply_to(m, "✅ **Logged in successfully!**")
        else: bot.reply_to(m, "❌ Invalid token.")
    except: bot.reply_to(m, "🧨 Connection error.")

# --- IMAGE HANDLER (Adds to Queue) ---
@bot.message_handler(content_types=['photo'])
def queue_images(m):
    uid = m.chat.id
    token = load_token(uid)
    
    if not token:
        return bot.reply_to(m, "❌ Use `/login` first.")

    # Create a placeholder message so user knows it is in line
    q_size = task_queue.qsize() + 1
    status = bot.reply_to(m, f"📥 **Added to Queue (Position: {q_size})**\nWaiting for processing...")
    
    # Add data to the background "Waiting Line"
    task_queue.put((uid, m.photo[-1].file_id, status.message_id, token))

print("AnimeGenius Sequential Bot is running...")
bot.infinity_polling()
