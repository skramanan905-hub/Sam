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

# Task Queue & Storage
task_queue = queue.Queue()
SESSION_FILE = "live3d_sessions.json"

# --- FLASK HEALTH CHECK (Same as goo.py logic) ---
app = Flask(__name__)

@app.route('/')
def index():
    return "AnimeGenius Bot is Active"

def run_flask():
    # Render requires a web server to stay alive
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- TOKEN HELPERS ---
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
            try: data = json.load(f)
            except: data = {}
    data[str(uid)] = token
    with open(SESSION_FILE, "w") as f:
        json.dump(data, f, indent=4)

# --- BACKGROUND WORKER (Processes images one-by-one) ---
def worker():
    while True:
        task = task_queue.get()
        if task is None: break
        
        chat_id, file_id, status_msg_id, token = task
        
        try:
            file_info = bot.get_file(file_id)
            img_content = bot.download_file(file_info.file_path)
            
            # Convert to Base64
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
                try:
                    tag_data = res.json()
                    prompt = tag_data.get('data', 'No tags returned.')
                    
                    # Fetch Points Update
                    b_res = requests.post(VERIFY_URL, headers=headers, json={})
                    points = b_res.json().get('points', '??')

                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_msg_id,
                        text=f"📝 **Prompt:**\n`{prompt}`\n\n💰 **Remaining:** `{points}` Points",
                        parse_mode="Markdown"
                    )
                except:
                    bot.edit_message_text("❌ Error reading API response.", chat_id, status_msg_id)
            elif res.status_code == 429:
                # Server is overloaded, put back in queue and wait
                time.sleep(10)
                task_queue.put(task)
            else:
                bot.edit_message_text(f"❌ API Error: {res.status_code}", chat_id, status_msg_id)

        except Exception as e:
            print(f"Worker Error: {e}")
        
        time.sleep(2.5) # Crucial pacing to prevent ban
        task_queue.task_done()

# --- BOT HANDLERS ---
@bot.message_handler(commands=['start'])
def start(m):
    bot.reply_to(m, "🤖 **AnimeGenius Img2Prompt Bot**\n\n1. Use `/login YOUR_TOKEN` to start.\n2. Send images (even 50+ at once). They will process one-by-one.")

@bot.message_handler(commands=['login'])
def login(m):
    args = m.text.split()
    if len(args) < 2:
        return bot.reply_to(m, "❌ Use: `/login [token]`")
    
    token = args[1].replace("Bearer ", "").strip()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    try:
        res = requests.post(VERIFY_URL, headers=headers, json={})
        if res.status_code == 200:
            save_token(m.chat.id, token)
            bot.reply_to(m, f"✅ **Login Success!**\n💰 Points: `{res.json().get('points')}`")
        else:
            bot.reply_to(m, "❌ Invalid Token.")
    except:
        bot.reply_to(m, "🧨 Connection failed.")

@bot.message_handler(content_types=['photo'])
def handle_photos(m):
    uid = m.chat.id
    token = load_token(uid)
    if not token:
        return bot.reply_to(m, "❌ Please `/login` first.")

    q_pos = task_queue.qsize() + 1
    status = bot.reply_to(m, f"📥 **Queued at Position: {q_pos}**")
    
    # Add to the one-by-one line
    task_queue.put((uid, m.photo[-1].file_id, status.message_id, token))

if __name__ == "__main__":
    # --- RENDER FIX: CLEAR OLD SESSIONS ---
    print("🚀 Removing old webhooks...")
    bot.delete_webhook(drop_pending_updates=True) # Fixed function name
    
    # Start background worker thread
    threading.Thread(target=worker, daemon=True).start()
    
    # Start Flask for Render Health Check
    Thread(target=run_flask).start()
    
    print("✅ Bot is Polling...")
    bot.infinity_polling()
