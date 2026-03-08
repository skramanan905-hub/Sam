import telebot
import requests
import time
import json
import os
import threading
from flask import Flask
from telebot import types

# --- RENDER HEALTH CHECK SERVER ---
app = Flask('')

@app.route('/')
def home():
    return "PixAI Bot is Online"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- CONFIGURATION ---
TG_TOKEN = "8560409798:AAF_bcLa-g9W_XglVTBV2wWdOzau1cyrH_E"
TG_CHAT_ID = "1827265590"

API_URL = "https://api.pixai.art/graphql"
BROWSER_ID = "32388bf0444e9a27c05474878ab23d97"
UA = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Mobile Safari/537.36"

# Hashes from your Reqable logs
HASH_GEN    = "61b5dafa7ade64f847051cdca7024b359bae652421834b8f78423d7640f17d96"
HASH_POLL   = "a32947c6b546befddacd08a3af63cc4ee2277af27fd43342a01fc0414fca3e8a"
HASH_LORA   = "4e1614f7373d676cb8ec17975796188369ce321a6e78336558ec50f0c2317840"
HASH_REWARD = "923002464a8e816706394061c18316cd2d14f5f025dbd1d08020e44cd8a23546"
HASH_CREDIT = "5bd29d8deb9cfd846370a5138d99179e6b8484e176396e478d5954045cf52981"

bot = telebot.TeleBot(TG_TOKEN)
user_data = {} # Stores user sessions

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
    params = {"operationName": "getGenerationModel", "variables": json.dumps({"id": lora_id}),
              "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": HASH_LORA}})}
    try:
        res = requests.get(API_URL, params=params, headers=get_headers(token), timeout=10).json()
        version = res['data']['generationModel']['latestAvailableVersion']
        return {"id": version['id'], "trigger": version['extra'].get('triggerWords', "")}
    except: return None

# --- BOT HANDLERS ---

@bot.message_handler(commands=['start'])
def welcome(message):
    uid = message.chat.id
    user_data[uid] = {'token': None, 'model': '1861558740588989558'}
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔑 Login", "💰 Balance")
    markup.add("🎨 Generate Image", "🎁 Claim Rewards")
    
    bot.send_message(uid, "✨ **PixAI Pro App (Render Edition)**\n\nPlease login with your token.", reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🔑 Login")
def login_init(message):
    msg = bot.send_message(message.chat.id, "Paste your `user_token` below:")
    bot.register_next_step_handler(msg, login_save)

def login_save(message):
    token = message.text.replace("user_token=", "").replace("Bearer ", "").strip()
    user_data[message.chat.id]['token'] = token
    bot.send_message(message.chat.id, "✅ Token Saved!")

@bot.message_handler(func=lambda m: m.text == "💰 Balance")
def check_bal(message):
    uid = message.chat.id
    u = user_data.get(uid)
    if not u or not u['token']: return bot.send_message(uid, "❌ Please login first.")
    
    params = {"operationName": "listMyQuotaLogs", "variables": json.dumps({"last": 1}),
              "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": HASH_CREDIT}})}
    try:
        res = requests.get(API_URL, params=params, headers=get_headers(u['token']), timeout=10).json()
        bal = res['data']['me']['quotaLogs']['edges'][0]['node']['extra']['originalBalance']
        bot.send_message(uid, f"💎 **Current Balance:** `{bal}` Credits")
    except: bot.send_message(uid, "❌ Failed to fetch balance.")

@bot.message_handler(func=lambda m: m.text == "🎁 Claim Rewards")
def claim(message):
    uid = message.chat.id
    u = user_data.get(uid)
    if not u or not u['token']: return bot.send_message(uid, "❌ Please login first.")
    
    bot.send_message(uid, "⏳ Claiming rewards...")
    for p in ["tiktok", "youtube", "instagram", "twitter", "discord"]:
        payload = {"operationName": "followSocialMedia", "variables": {"platform": p},
                   "extensions": {"persistedQuery": {"version": 1, "sha256Hash": HASH_REWARD}}}
        requests.post(API_URL, json=payload, headers=get_headers(u['token']), timeout=10)
    bot.send_message(uid, "✅ All daily social rewards claimed!")

# --- DYNAMIC GENERATION FLOW ---

@bot.message_handler(func=lambda m: m.text == "🎨 Generate Image")
def gen_step_1(message):
    uid = message.chat.id
    if not user_data.get(uid, {}).get('token'): return bot.send_message(uid, "❌ Login first.")
    msg = bot.send_message(uid, "📝 **STEP 1:** Enter your prompt:")
    bot.register_next_step_handler(msg, gen_step_2)

def gen_step_2(message):
    uid = message.chat.id
    user_data[uid]['current_prompt'] = message.text
    msg = bot.send_message(uid, "🧬 **STEP 2:** Enter LoRA IDs (space separated) or type 'none':")
    bot.register_next_step_handler(msg, gen_step_3)

def gen_step_3(message):
    uid = message.chat.id
    user_data[uid]['lora_input'] = [] if message.text.lower() == 'none' else message.text.split()
    msg = bot.send_message(uid, "🔢 **STEP 3:** Enter Batch Size (1, 2, 3, or 4):")
    bot.register_next_step_handler(msg, process_final_gen)

def process_final_gen(message):
    uid = message.chat.id
    try:
        batch = int(message.text)
        if batch < 1 or batch > 4: raise ValueError
    except:
        return bot.send_message(uid, "❌ Invalid batch size. Choose 1 to 4. Start over.")

    u = user_data[uid]
    status_msg = bot.send_message(uid, "🚀 **Requesting PixAI Engine...**")

    # 1. Handle LoRAs
    l_params, l_weights, triggers = [], {}, ""
    for lid in u['lora_input']:
        meta = fetch_lora_metadata(u['token'], lid)
        if meta:
            l_weights[meta['id']] = 0.7
            if meta['trigger']: triggers += f", {meta['trigger']}"
            l_params.append({"versionId": meta['id'], "weight": 0.7, "triggerWords": meta['trigger'], "positionInfo": {"startIndex": 0, "endIndex": 0}})

    # 2. Submit Generation
    payload = {
        "operationName": "createGenerationTask",
        "variables": {
            "parameters": {
                "prompts": u['current_prompt'] + triggers,
                "modelId": u['model'], "width": 512, "height": 1024, "batchSize": batch,
                "lora": l_weights, "loraParameters": l_params,
                "samplingSteps": 28, "samplingMethod": "Euler a", "cfgScale": 5,
                "promptHelper": {"withStage": True, "userWantToEnable": True, "enable": True}
            }
        },
        "extensions": {"persistedQuery": {"version": 1, "sha256Hash": HASH_GEN}}
    }

    try:
        res = requests.post(API_URL, json=payload, headers=get_headers(u['token']), timeout=15).json()
        if "errors" in res:
            return bot.edit_message_text(f"❌ API Error: {res['errors'][0]['message']}", uid, status_msg.id)

        task_id = res['data']['createGenerationTask']['id']
        bot.edit_message_text(f"🎨 **Rendering...**\nTask ID: `{task_id}`", uid, status_msg.id)

        # 3. Polling Status
        while True:
            time.sleep(10)
            poll = {"operationName": "getTaskById", "variables": json.dumps({"id": task_id}),
                    "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": HASH_POLL}})}
            s_res = requests.get(API_URL, params=poll, headers=get_headers(u['token']), timeout=10).json()
            task = s_res['data']['task']

            if task['status'] == "completed":
                bot.delete_message(uid, status_msg.id)
                for img in task['media']['urls']:
                    if img['variant'] == "PUBLIC":
                        bot.send_photo(uid, img['url'], caption=f"✅ Done!\nPrompt: {u['current_prompt']}")
                break
            elif task['status'] == "failed":
                bot.edit_message_text("❌ Server-side render failed.", uid, status_msg.id)
                break
    except Exception as e:
        bot.send_message(uid, f"❌ Bot Crash: {e}")

# --- START SERVICE ---
if __name__ == "__main__":
    # Start Render keep-alive server
    threading.Thread(target=run_web).start()
    
    print("PixAI App Bot is running and connected to Render...")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
