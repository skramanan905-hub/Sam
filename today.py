import telebot
import requests
import time
import json
import os
import threading
from flask import Flask
from telebot import types

# --- RENDER WEB SERVER ---
# This part tells Render the bot is a "Web Service" so it stays alive.
server = Flask('')

@server.route('/')
def home():
    return "PixAI Bot Status: 100% Stable and Online"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server.run(host='0.0.0.0', port=port)

# ================= CONFIGURATION =================
API_TOKEN = "8560409798:AAF_bcLa-g9W_XglVTBV2wWdOzau1cyrH_E"
bot = telebot.TeleBot(API_TOKEN)

user_data = {} 

# Hashes extracted from your logs
HASH_GEN    = "61b5dafa7ade64f847051cdca7024b359bae652421834b8f78423d7640f17d96"
HASH_POLL   = "a32947c6b546befddacd08a3af63cc4ee2277af27fd43342a01fc0414fca3e8a"
HASH_LORA   = "4e1614f7373d676cb8ec17975796188369ce321a6e78336558ec50f0c2317840"
HASH_REWARD = "923002464a8e816706394061c18316cd2d14f5f025dbd1d08020e44cd8a23546"
HASH_CREDIT = "5bd29d8deb9cfd846370a5138d99179e6b8484e176396e478d5954045cf52981"

API_URL = "https://api.pixai.art/graphql"
BROWSER_ID = "32388bf0444e9a27c05474878ab23d97"
UA = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Mobile Safari/537.36"

# --- HELPERS ---

def get_headers(token):
    return {
        "Authorization": f"Bearer {token.strip()}",
        "Content-Type": "application/json",
        "x-browser-id": BROWSER_ID,
        "User-Agent": UA,
        "Origin": "https://pixai.art"
    }

def fetch_lora_metadata(token, lora_id):
    """Fetches real Version ID and Trigger Words"""
    params = {"operationName": "getGenerationModel", "variables": json.dumps({"id": lora_id}),
              "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": HASH_LORA}})}
    try:
        res = requests.get(API_URL, params=params, headers=get_headers(token), timeout=10).json()
        if not res or 'data' not in res: return None
        version_data = res['data']['generationModel']['latestAvailableVersion']
        return {
            "versionId": version_data['id'],
            "triggerWords": version_data['extra'].get('triggerWords', "")
        }
    except: return None

# --- TELEGRAM COMMANDS ---

@bot.message_handler(commands=['start'])
def welcome(message):
    uid = message.chat.id
    user_data[uid] = {'token': None, 'model': '1861558740588989558'}
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔑 Login", "💰 Check Credits")
    markup.add("🎨 Start Generating", "🎁 Claim Daily")
    bot.send_message(uid, "🚀 **PixAI Pro App Console**\nWelcome! Please login to start.", reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🔑 Login")
def ask_token(message):
    msg = bot.send_message(message.chat.id, "Paste your `user_token` below:")
    bot.register_next_step_handler(msg, save_token)

def save_token(message):
    uid = message.chat.id
    token = message.text.replace("user_token=", "").replace("Bearer ", "").strip()
    if uid not in user_data: user_data[uid] = {'model': '1861558740588989558'}
    user_data[uid]['token'] = token
    bot.send_message(uid, "✅ Token Saved!")

@bot.message_handler(func=lambda m: m.text == "💰 Check Credits")
def check_credits(message):
    uid = message.chat.id
    u = user_data.get(uid)
    if not u or not u.get('token'): return bot.send_message(uid, "❌ Please login first.")
    
    params = {"operationName": "listMyQuotaLogs", "variables": json.dumps({"last": 1}),
              "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": HASH_CREDIT}})}
    try:
        res = requests.get(API_URL, params=params, headers=get_headers(u['token']), timeout=10).json()
        bal = res['data']['me']['quotaLogs']['edges'][0]['node']['extra']['originalBalance']
        bot.send_message(uid, f"💎 **Balance:** `{bal}` Credits")
    except: bot.send_message(uid, "❌ Error checking balance. Token might be expired.")

@bot.message_handler(func=lambda m: m.text == "🎁 Claim Daily")
def claim_rewards(message):
    uid = message.chat.id
    u = user_data.get(uid)
    if not u or not u.get('token'): return bot.send_message(uid, "❌ Please login first.")
    bot.send_message(uid, "⏳ Claiming rewards...")
    for p in ["tiktok", "youtube", "instagram", "twitter", "discord"]:
        payload = {"operationName": "followSocialMedia", "variables": {"platform": p},
                   "extensions": {"persistedQuery": {"version": 1, "sha256Hash": HASH_REWARD}}}
        requests.post(API_URL, json=payload, headers=get_headers(u['token']), timeout=10)
    bot.send_message(uid, "✅ Rewards claimed!")

# --- FLOW: PROMPT -> LORA -> BATCH ---

@bot.message_handler(func=lambda m: m.text == "🎨 Start Generating")
def gen_step1(message):
    uid = message.chat.id
    if not user_data.get(uid, {}).get('token'): return bot.send_message(uid, "❌ Please login first.")
    msg = bot.send_message(uid, "📝 **STEP 1:** Enter your **Prompt**:")
    bot.register_next_step_handler(msg, gen_step2)

def gen_step2(message):
    uid = message.chat.id
    user_data[uid]['prompt'] = message.text
    msg = bot.send_message(uid, "🧬 **STEP 2:** Enter **LoRA IDs** (separate with space) or type 'none':")
    bot.register_next_step_handler(msg, gen_step3)

def gen_step3(message):
    uid = message.chat.id
    user_data[uid]['loras'] = [] if message.text.lower() == 'none' else message.text.split()
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("1", "2", "3", "4")
    msg = bot.send_message(uid, "🔢 **STEP 3:** Choose **Batch Size** (1-4):", reply_markup=markup)
    bot.register_next_step_handler(msg, process_gen_final)

def process_gen_final(message):
    uid = message.chat.id
    u = user_data[uid]
    try: batch = int(message.text)
    except: batch = 1

    # Back to main menu buttons
    main_menu = types.ReplyKeyboardMarkup(resize_keyboard=True)
    main_menu.add("🔑 Login", "💰 Check Credits", "🎨 Start Generating", "🎁 Claim Daily")
    bot.send_message(uid, f"🛰 **Requesting PixAI to generate {batch} images...**", reply_markup=main_menu)
    
    # 1. Prepare LoRA Triggers
    l_params, l_weights, triggers = [], {}, ""
    for lid in u['loras']:
        meta = fetch_lora_metadata(u['token'], lid)
        if meta:
            l_weights[meta['versionId']] = 0.7
            triggers += f", {meta['triggerWords']}"
            l_params.append({
                "versionId": meta['versionId'], "weight": 0.7, "triggerWords": meta['triggerWords'],
                "positionInfo": {"startIndex": 0, "endIndex": 0}
            })

    # 2. Submit Generation Task
    payload = {
        "operationName": "createGenerationTask",
        "variables": {
            "parameters": {
                "prompts": u['prompt'] + triggers,
                "modelId": u['model'], "width": 512, "height": 1024, "batchSize": batch,
                "lora": l_weights, "loraParameters": l_params,
                "samplingSteps": 28, "samplingMethod": "Euler a", "cfgScale": 5,
                "promptHelper": {"withStage": True, "userWantToEnable": True, "enable": True}
            }
        },
        "extensions": {"persistedQuery": {"version": 1, "sha256Hash": HASH_GEN}}
    }

    try:
        response = requests.post(API_URL, json=payload, headers=get_headers(u['token']), timeout=20)
        res = response.json()
        
        # ERROR PROTECTION: Check if res has 'data'
        if not res or 'data' not in res or res['data'] is None:
            err = res.get('errors', [{'message': 'Server blocked Render IP or token expired'}])[0]['message']
            return bot.send_message(uid, f"❌ **Error:** {err}")

        task_id = res['data']['createGenerationTask']['id']
        bot.send_message(uid, f"🎨 **Rendering...**\nID: `{task_id}`")

        # 3. Polling for Status
        while True:
            time.sleep(10)
            poll_params = {"operationName": "getTaskById", "variables": json.dumps({"id": task_id}),
                           "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": HASH_POLL}})}
            s_res = requests.get(API_URL, params=poll_params, headers=get_headers(u['token']), timeout=15).json()
            
            if not s_res or 'data' not in s_res or s_res['data'] is None: continue
            
            task = s_res['data']['task']
            if task['status'] == "completed":
                for img in task['media']['urls']:
                    if img['variant'] == "PUBLIC":
                        bot.send_photo(uid, img['url'], caption=f"✨ **Generation Success!**")
                break
            elif task['status'] == "failed":
                bot.send_message(uid, "❌ PixAI failed to render this task.")
                break
    except Exception as e:
        bot.send_message(uid, f"❌ System Error: {e}")

# --- START EXECUTION ---
if __name__ == "__main__":
    # Start the Flask Health Server in a separate thread for Render
    threading.Thread(target=run_web_server).start()
    print("Render Health server started.")
    
    print("--- BOT IS ONLINE ---")
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
