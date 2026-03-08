import telebot
import requests
import time
import json
import os
from telebot import types

# ================= CONFIGURATION =================
API_TOKEN = "8560409798:AAF_bcLa-g9W_XglVTBV2wWdOzau1cyrH_E"
bot = telebot.TeleBot(API_TOKEN)

user_data = {} 

# Static Hashes from your logs
HASH_GEN    = "61b5dafa7ade64f847051cdca7024b359bae652421834b8f78423d7640f17d96"
HASH_POLL   = "a32947c6b546befddacd08a3af63cc4ee2277af27fd43342a01fc0414fca3e8a"
HASH_LORA   = "4e1614f7373d676cb8ec17975796188369ce321a6e78336558ec50f0c2317840"
HASH_REWARD = "923002464a8e816706394061c18316cd2d14f5f025dbd1d08020e44cd8a23546"
HASH_CREDIT = "5bd29d8deb9cfd846370a5138d99179e6b8484e176396e478d5954045cf52981"

# --- HELPERS ---

def get_headers(token):
    return {
        "Authorization": f"Bearer {token.strip()}",
        "Content-Type": "application/json",
        "x-browser-id": "32388bf0444e9a27c05474878ab23d97",
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Mobile Safari/537.36"
    }

def fetch_lora_info(token, lora_id):
    params = {"operationName": "getGenerationModel", "variables": json.dumps({"id": lora_id}),
              "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": HASH_LORA}})}
    try:
        res = requests.get("https://api.pixai.art/graphql", params=params, headers=get_headers(token)).json()
        ver = res['data']['generationModel']['latestAvailableVersion']
        return {"id": ver['id'], "trigger": ver['extra'].get('triggerWords', "")}
    except: return None

# --- COMMANDS ---

@bot.message_handler(commands=['start'])
def welcome(message):
    uid = message.chat.id
    user_data[uid] = {'token': None, 'model': '1861558740588989558'}
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔑 Login", "💰 Check Credits")
    markup.add("🎨 Start Generating", "🎁 Claim Daily")
    
    bot.send_message(uid, "🚀 **PixAI Pro Console Bot**\nWelcome!", reply_markup=markup, parse_mode="Markdown")

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
    if not u or not u['token']: return bot.send_message(uid, "❌ Log in first!")
    
    params = {"operationName": "listMyQuotaLogs", "variables": json.dumps({"last": 1}),
              "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": HASH_CREDIT}})}
    try:
        res = requests.get("https://api.pixai.art/graphql", params=params, headers=get_headers(u['token'])).json()
        bal = res['data']['me']['quotaLogs']['edges'][0]['node']['extra']['originalBalance']
        bot.send_message(uid, f"💎 **Balance:** `{bal}` Credits")
    except: bot.send_message(uid, "❌ Error checking balance.")

@bot.message_handler(func=lambda m: m.text == "🎁 Claim Daily")
def claim_daily(message):
    uid = message.chat.id
    u = user_data.get(uid)
    if not u or not u['token']: return bot.send_message(uid, "❌ Log in first!")
    
    bot.send_message(uid, "⏳ Claiming rewards...")
    for p in ["tiktok", "youtube", "instagram", "twitter", "discord"]:
        payload = {"operationName": "followSocialMedia", "variables": {"platform": p},
                   "extensions": {"persistedQuery": {"version": 1, "sha256Hash": HASH_REWARD}}}
        requests.post("https://api.pixai.art/graphql", json=payload, headers=get_headers(u['token']))
    bot.send_message(uid, "✅ Rewards claimed!")

# --- GENERATION FLOW ---

@bot.message_handler(func=lambda m: m.text == "🎨 Start Generating")
def gen_init(message):
    uid = message.chat.id
    if not user_data.get(uid, {}).get('token'): return bot.send_message(uid, "❌ Log in first!")
    msg = bot.send_message(uid, "📝 **STEP 1:** Enter your prompt:")
    bot.register_next_step_handler(msg, get_prompt)

def get_prompt(message):
    uid = message.chat.id
    user_data[uid]['prompt'] = message.text
    msg = bot.send_message(uid, "🧬 **STEP 2:** Enter LoRA IDs (separate with space) or type 'none':")
    bot.register_next_step_handler(msg, get_batch)

def get_batch(message):
    uid = message.chat.id
    user_data[uid]['loras'] = [] if message.text.lower() == 'none' else message.text.split()
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("1", "2", "3", "4")
    msg = bot.send_message(uid, "🔢 **STEP 3:** Choose Batch Size (1-4):", reply_markup=markup)
    bot.register_next_step_handler(msg, start_pixai_process)

def start_pixai_process(message):
    uid = message.chat.id
    u = user_data[uid]
    
    try:
        batch = int(message.text)
        if batch < 1 or batch > 4: batch = 1
    except:
        batch = 1

    # Main menu keyboard reset
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔑 Login", "💰 Check Credits")
    markup.add("🎨 Start Generating", "🎁 Claim Daily")
    
    bot.send_message(uid, f"🛰 **Processing Batch of {batch}...**", reply_markup=markup)
    
    # 1. Fetch Triggers
    l_params, l_weights, triggers = [], {}, ""
    for lid in u['loras']:
        meta = fetch_lora_info(u['token'], lid)
        if meta:
            l_weights[meta['id']] = 0.7
            triggers += f", {meta['trigger']}"
            l_params.append({"versionId": meta['id'], "weight": 0.7, "triggerWords": meta['trigger'], "positionInfo": {"startIndex": 0, "endIndex": 0}})

    # 2. Submit
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
        res = requests.post("https://api.pixai.art/graphql", json=payload, headers=get_headers(u['token'])).json()
        if "errors" in res:
            return bot.send_message(uid, f"❌ Error: {res['errors'][0]['message']}")

        task_id = res['data']['createGenerationTask']['id']
        bot.send_message(uid, f"🎨 **Rendering...**\nTask ID: `{task_id}`")

        # 3. Polling Loop
        while True:
            time.sleep(10)
            poll_params = {"operationName": "getTaskById", "variables": json.dumps({"id": task_id}),
                           "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": HASH_POLL}})}
            s_res = requests.get("https://api.pixai.art/graphql", params=poll_params, headers=get_headers(u['token'])).json()
            task = s_res['data']['task']

            if task['status'] == "completed":
                for img in task['media']['urls']:
                    if img['variant'] == "PUBLIC":
                        bot.send_photo(uid, img['url'], caption="✨ Generation Success!")
                break
            elif task['status'] == "failed":
                bot.send_message(uid, "❌ Generation failed on server.")
                break
    except Exception as e:
        bot.send_message(uid, f"❌ Error: {e}")

# --- START ---
print("--- BOT IS ONLINE ---")
bot.infinity_polling()
