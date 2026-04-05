import telebot
import requests
import base64
import json
import os
import time
import queue
import threading
from flask import Flask
from threading import Thread

# ================= CONFIGURATION =================
API_TOKEN = "8748542024:AAHbhNJHZP8Tdo_OLam-h6CJGMG9S5n6MDU"
bot = telebot.TeleBot(API_TOKEN)

# Live3D API Endpoints
VERIFY_URL = "https://api.live3d.io/api/v1/verify_token"
TAGGER_URL = "https://api.live3d.io/api/v1/generation/img2prompt"

# Task Queue System
task_queue = queue.Queue()
SESSION_FILE = "live3d_sessions.json"

# --- RENDER KEEP-ALIVE SERVER ---
server = Flask('')
@server.route('/')
def home(): return "Bot is Alive!"

def run_web():
    # Render uses the PORT environment variable
    port = int(os.environ.get("PORT", 8080))
    server.run(host='0.0.0.0', port=port)

# --- SESSION HELPERS ---
def load_token(uid):
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, "r") as f:
                return json.load(f).get(str(uid))
        except: return None
    return None

def save_token(uid, token):
    data = {}
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, "r") as f:
            data = json.load(f)
    data[str(uid)] = token
    with open(SESSION_FILE, "w") as f:
        json.dump(data, f, indent=4)

# --- THE BACKGROUND WORKER (Processes 50+ images one-by-one) ---
def worker():
    while True:
        task = task_queue.get()
        if task is None: break
        
        chat_id, file_id, status_msg_id, token = task
        
        try:
            file_info = bot.get_file(file_id)
            img_content = bot.download_file(file_info.file_path)
            
            encoded = base64.b64encode(img_content).decode('utf-8')
            base64_payload = f"data:image/webp;base64,{encoded}"

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Origin": "https://animegenius.live3d.io",
                "Referer": "https://animegenius.live3d.io/"
            }
            
            res = requests.post(TAGGER_URL, headers=headers, json={"image": base64_payload, "consume_points": 1})
            
            if res.status_code == 200:
                tag_data = res.json()
                prompt = tag_data.get('data', 'No tags returned.')
                
                # Update coins
                b_res = requests.post(VERIFY_URL, headers=headers, json={})
                points = b_res.json().get('points', '??')

                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_msg_id,
                    text=f"📝 **Prompt:**\n`{prompt}`\n\n💰 **Remaining:** `{points}` Points",
                    parse_mode="Markdown"
                )
            elif res.status_code == 429:
                bot.edit_message_text(f"⚠️ Server busy. Retrying in 10s...", chat_id, status_msg_id)
                time.sleep(10)
                task_queue.put(task)
            else:
                bot.edit_message_text(f"❌ API Error: {res.status_code}", chat_id, status_msg_id)

        except Exception as e:
            try: bot.edit_message_text(f"🧨 Error: {str(e)}", chat_id, status_msg_id)
            except: pass
        
        time.sleep(2.5) # Anti-ban safety pacing
        task_queue.task_done()

# Start background thread
threading.Thread(target=worker, daemon=True).start()

# --- BOT COMMANDS ---
@bot.message_handler(commands=['start'])
def start(m):
    bot.reply_to(m, "🤖 **AnimeGenius Queue Bot**\n\nUse `/login YOUR_TOKEN` first.\nThen send images.")

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
            bot.reply_to(m, "✅ **Logged in!**")
        else: bot.reply_to(m, "❌ Invalid token.")
    except: bot.reply_to(m, "🧨 Connection error.")

@bot.message_handler(content_types=['photo'])
def queue_images(m):
    uid = m.chat.id
    token = load_token(uid)
    if not token: return bot.reply_to(m, "❌ Use `/login` first.")

    q_size = task_queue.qsize() + 1
    status = bot.reply_to(m, f"📥 **In Queue (Pos: {q_size})**")
    task_queue.put((uid, m.photo[-1].file_id, status.message_id, token))

if __name__ == "__main__":
    # --- RENDER RESTART FIX ---
    print("🚀 Fixing Telegram Conflict (409)...")
    bot.remove_webhook(drop_pending_updates=True)
    time.sleep(1) 
    
    # Start Keep-Alive Server
    Thread(target=run_web).start()
    
    print("✅ Bot is starting...")
    bot.infinity_polling(timeout=60, long_polling_timeout=5)
