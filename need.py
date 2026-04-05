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
bot = telebot.TeleBot(API_TOKEN, threaded=False) # threaded=False is more stable for Render

# Live3D API Endpoints
VERIFY_URL = "https://api.live3d.io/api/v1/verify_token"
TAGGER_URL = "https://api.live3d.io/api/v1/generation/img2prompt"

task_queue = queue.Queue()
SESSION_FILE = "live3d_sessions.json"

# --- RENDER HEALTH CHECK (Flask) ---
app = Flask(__name__)
@app.route('/')
def index(): return "AnimeGenius Bot is Active"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- TOKEN HELPERS ---
def load_token(uid):
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, "r") as f:
            return json.load(f).get(str(uid))
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

# --- WORKER LOGIC ---
def worker():
    while True:
        task = task_queue.get()
        if task is None: break
        uid, fid, mid, tok = task
        try:
            f_info = bot.get_file(fid)
            img = bot.download_file(f_info.file_path)
            b64 = base64.b64encode(img).decode('utf-8')
            h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json", "Origin": "https://animegenius.live3d.io", "Referer": "https://animegenius.live3d.io/"}
            
            r = requests.post(TAGGER_URL, headers=h, json={"image": f"data:image/webp;base64,{b64}", "consume_points": 1})
            if r.status_code == 200:
                tags = r.json().get('data', 'No tags.')
                pts = requests.post(VERIFY_URL, headers=h, json={}).json().get('points', '??')
                bot.edit_message_text(f"📝 **Prompt:**\n`{tags}`\n\n💰 **Remaining:** `{pts}` Points", uid, mid, parse_mode="Markdown")
            elif r.status_code == 429:
                time.sleep(10)
                task_queue.put(task)
            else:
                bot.edit_message_text(f"❌ API Error: {r.status_code}", uid, mid)
        except Exception as e:
            print(f"Worker Error: {e}")
        time.sleep(2.5)
        task_queue.task_done()

# --- BOT HANDLERS ---
@bot.message_handler(commands=['start'])
def start(m):
    bot.reply_to(m, "🤖 **AnimeGenius Bot Ready**\nSend `/login TOKEN` and then your images.")

@bot.message_handler(commands=['login'])
def login(m):
    args = m.text.split()
    if len(args) < 2: return bot.reply_to(m, "❌ Use: `/login [token]`")
    t = args[1].replace("Bearer ", "").strip()
    try:
        r = requests.post(VERIFY_URL, headers={"Authorization": f"Bearer {t}"}, json={})
        if r.status_code == 200:
            save_token(m.chat.id, t)
            bot.reply_to(m, f"✅ Login Success! Points: {r.json().get('points')}")
        else: bot.reply_to(m, "❌ Invalid Token.")
    except: bot.reply_to(m, "🧨 Connection failed.")

@bot.message_handler(content_types=['photo'])
def handle_photos(m):
    tok = load_token(m.chat.id)
    if not tok: return bot.reply_to(m, "❌ Please `/login` first.")
    status = bot.reply_to(m, "📥 **Added to Queue...**")
    task_queue.put((m.chat.id, m.photo[-1].file_id, status.message_id, tok))

# --- MASTER STARTUP ---
if __name__ == "__main__":
    # 1. Start Render Health Check (Main Thread Requirement)
    Thread(target=run_flask).start()
    
    # 2. Start Worker
    Thread(target=worker, daemon=True).start()

    # 3. FIX CONFLICT (Clear old Render processes)
    print("🛰 Cleaning session...")
    bot.remove_webhook()
    time.sleep(2) # Give Render time to kill the old bot

    print("✅ Bot is Starting...")
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f"Polling Error: {e}")
            time.sleep(5) # Auto-restart if 409 occurs
