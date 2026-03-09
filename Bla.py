import telebot
import requests
import time
import json
import random # For human-like delays
import threading
from flask import Flask
from telebot import types

app = Flask('')
@app.route('/')
def home(): return "Bot is Stealthily Online"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- CONFIG ---
API_TOKEN = "8560409798:AAF_bcLa-g9W_XglVTBV2wWdOzau1cyrH_E"
bot = telebot.TeleBot(API_TOKEN)
user_data = {} 

API_URL = "https://api.pixai.art/graphql"
BROWSER_ID = "32388bf0444e9a27c05474878ab23d97"
UA = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Mobile Safari/537.36"

# --- STEALTH HELPERS ---

def get_headers(token):
    return {
        "Authorization": f"Bearer {token.strip()}",
        "Content-Type": "application/json",
        "x-browser-id": BROWSER_ID,
        "User-Agent": UA,
        "Origin": "https://pixai.art",
        "Referer": "https://pixai.art/generator/image" # Added to look more real
    }

def safe_request(method, url, **kwargs):
    """A professional wrapper to handle PixAI slowness/blocking"""
    for i in range(3): # Try 3 times before giving up
        try:
            time.sleep(random.uniform(1.5, 3.0)) # Random delay like a human
            response = requests.request(method, url, **kwargs)
            if response.status_code == 200:
                data = response.json()
                if 'data' in data and data['data'] is not None:
                    return data
            elif response.status_code == 429: # Too many requests
                time.sleep(10)
        except:
            time.sleep(5)
    return None

# --- [Login/Balance/Claim functions remain the same as previous code] ---
# ... (I will focus on the fixed Generation Flow below)

@bot.message_handler(func=lambda m: m.text == "🎨 Start Generating")
def gen_init(message):
    uid = message.chat.id
    msg = bot.send_message(uid, "📝 **STEP 1:** Enter your prompt:")
    bot.register_next_step_handler(msg, get_prompt)

def get_prompt(message):
    user_data[message.chat.id]['prompt'] = message.text
    msg = bot.send_message(message.chat.id, "🧬 **STEP 2:** Enter LoRA IDs or 'none':")
    bot.register_next_step_handler(msg, get_batch)

def get_batch(message):
    user_data[message.chat.id]['loras'] = [] if message.text.lower() == 'none' else message.text.split()
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("1", "2", "3", "4")
    msg = bot.send_message(message.chat.id, "🔢 **STEP 3:** Choose Batch Size:", reply_markup=markup)
    bot.register_next_step_handler(msg, start_gen)

def start_gen(message):
    uid = message.chat.id
    u = user_data[uid]
    batch = int(message.text) if message.text.isdigit() else 1
    
    status_msg = bot.send_message(uid, "🛰 **Communicating with PixAI...**")

    # [LoRA metadata fetching logic here using safe_request]
    # ... 

    # SUBMIT
    payload = {
        "operationName": "createGenerationTask",
        "variables": {
            "parameters": {
                "prompts": u['prompt'], # Triggers would be added here
                "modelId": "1861558740588989558", 
                "batchSize": batch, "width": 512, "height": 1024,
                "samplingSteps": 28, "samplingMethod": "Euler a", "cfgScale": 5
            }
        },
        "extensions": {"persistedQuery": {"version": 1, "sha256Hash": "61b5dafa7ade64f847051cdca7024b359bae652421834b8f78423d7640f17d96"}}
    }

    res = safe_request("POST", API_URL, json=payload, headers=get_headers(u['token']))
    
    if not res:
        return bot.edit_message_text("❌ **PixAI is too slow or blocked Render.** Try again in 1 minute.", uid, status_msg.id)

    task_id = res['data']['createGenerationTask']['id']
    bot.edit_message_text(f"🎨 **Rendering Batch...**\nID: `{task_id}`", uid, status_msg.id)

    # POLL
    while True:
        # Polling every 12 seconds is safer on Render than 5 seconds
        time.sleep(12) 
        poll_params = {"operationName": "getTaskById", "variables": json.dumps({"id": task_id}),
                       "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": "a32947c6b546befddacd08a3af63cc4ee2277af27fd43342a01fc0414fca3e8a"}})}
        
        poll_res = safe_request("GET", API_URL, params=poll_params, headers=get_headers(u['token']))
        if not poll_res: continue # Just keep trying if one request fails

        task = poll_res['data']['task']
        if task['status'] == "completed":
            bot.delete_message(uid, status_msg.id)
            for img in task['media']['urls']:
                if img['variant'] == "PUBLIC":
                    bot.send_photo(uid, img['url'])
            break
        elif task['status'] == "failed":
            bot.send_message(uid, "❌ PixAI failed.")
            break

# --- Start ---
if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    bot.infinity_polling()
