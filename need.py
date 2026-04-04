import telebot
import requests
import base64
import json
import os
import time
from flask import Flask
from threading import Thread

# ================= CONFIGURATION =================
API_TOKEN = "8748542024:AAHbhNJHZP8Tdo_OLam-h6CJGMG9S5n6MDU"
bot = telebot.TeleBot(API_TOKEN)

# Live3D Endpoints
VERIFY_URL = "https://api.live3d.io/api/v1/verify_token"
TAGGER_URL = "https://api.live3d.io/api/v1/generation/img2prompt"

# Local session storage
SESSION_FILE = "live3d_sessions.json"

# --- RENDER KEEP-ALIVE SERVER ---
app = Flask('')
@app.route('/')
def home(): return "Bot is Alive!"

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

# --- HELPERS ---
def get_token(uid):
    if os.path.exists(SESSION_FILE):
        return json.load(open(SESSION_FILE)).get(str(uid))
    return None

def save_token(uid, token):
    data = json.load(open(SESSION_FILE)) if os.path.exists(SESSION_FILE) else {}
    data[str(uid)] = token
    json.dump(data, open(SESSION_FILE, "w"), indent=4)

# --- BOT LOGIC ---
@bot.message_handler(commands=['start'])
def welcome(m):
    bot.reply_to(m, "🤖 **AnimeGenius Tagger Ready**\n\nSend `/login YOUR_TOKEN` to start.\nThen send any image (or multiple images).")

@bot.message_handler(commands=['login'])
def handle_login(m):
    args = m.text.split()
    if len(args) < 2:
        return bot.reply_to(m, "❌ **Error:** Use `/login your_bearer_token`")
    
    token = args[1].replace("Bearer ", "").strip()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    try:
        res = requests.post(VERIFY_URL, headers=headers, json={})
        d = res.json()
        if d.get("points") is not None:
            save_token(m.chat.id, token)
            bot.reply_to(m, f"✅ **Login Success!**\n💰 Points: `{d['points']}`")
        else:
            bot.reply_to(m, "❌ **Invalid Token.** Check your data.")
    except:
        bot.reply_to(m, "🧨 Connection failed.")

@bot.message_handler(content_types=['photo'])
def process_images(m):
    uid = m.chat.id
    token = get_token(uid)
    
    if not token:
        return bot.reply_to(m, "❌ **Access Denied:** Use `/login` first.")

    # Status message for one-by-one processing
    status_msg = bot.reply_to(m, "⏳ **Analyzing Image...**")

    try:
        # 1. Download image
        file_info = bot.get_file(m.photo[-1].file_id)
        image_bytes = bot.download_file(file_info.file_path)
        
        # 2. Convert to Base64 format required by Live3D
        b64_str = base64.b64encode(image_bytes).decode('utf-8')
        data_payload = {
            "image": f"data:image/webp;base64,{b64_str}",
            "consume_points": 1
        }

        # 3. Request Tags
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Origin": "https://animegenius.live3d.io",
            "Referer": "https://animegenius.live3d.io/"
        }
        
        res = requests.post(TAGGER_URL, headers=headers, json=data_payload)
        tags = res.json().get('data', 'No tags found.')

        # 4. Update Points
        bal_res = requests.post(VERIFY_URL, headers=headers, json={})
        points = bal_res.json().get('points', '??')

        # 5. Send Result
        bot.edit_message_text(
            chat_id=uid,
            message_id=status_msg.message_id,
            text=f"📝 **Prompt:**\n`{tags}`\n\n💰 **Remaining:** `{points}` Points",
            parse_mode="Markdown"
        )
        
        # Small sleep to ensure "one-by-one" feel if multiple images sent
        time.sleep(1)

    except Exception as e:
        bot.edit_message_text(f"🧨 **Error:** {str(e)}", uid, status_msg.message_id)

# --- START SERVICE ---
if __name__ == "__main__":
    # Start Flask in a separate thread so it doesn't block the Bot
    Thread(target=run_web).start()
    print("AnimeGenius Bot is running...")
    bot.infinity_polling()
