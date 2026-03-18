import telebot
import requests
import time
import json
import os
import threading
from flask import Flask
from telebot import types

# --- RENDER ALIVE SYSTEM (Required for Render Hosting) ---
server = Flask('')
@server.route('/')
def ping(): return "Bot is Online"

def run_web():
    # Render uses port 8080 by default
    port = int(os.environ.get("PORT", 8080))
    server.run(host='0.0.0.0', port=port)

# ================= CONFIGURATION =================
API_TOKEN = "8645010901:AAHcLKEPUkUkOwr7RT28ONQzo4tqzVURTfA"
bot = telebot.TeleBot(API_TOKEN)

SESSION_FILE = "session.json"
API_URL = "https://api.pixai.art/graphql"

# Static Hashes from your data
HASH_GEN    = "61b5dafa7ade64f847051cdca7024b359bae652421834b8f78423d7640f17d96"
HASH_POLL   = "a32947c6b546befddacd08a3af63cc4ee2277af27fd43342a01fc0414fca3e8a"
HASH_LORA   = "4e1614f7373d676cb8ec17975796188369ce321a6e78336558ec50f0c2317840"
HASH_REWARD = "923002464a8e816706394061c18316cd2d14f5f025dbd1d08020e44cd8a23546"
HASH_CREDIT = "5bd29d8deb9cfd846370a5138d99179e6b8484e176396e478d5954045cf52981"
HASH_LIST   = "cc067203ddd0846c19d9e247d837c32da498247ec252fe30828434f2f136f53d"
HASH_MEDIA  = "a32947c6b546befddacd08a3af63cc4ee2277af27fd43342a01fc0414fca3e8a" # getMedia hash

user_states = {}

# --- HELPERS ---

def get_headers(token):
    return {
        "Authorization": f"Bearer {token.strip()}",
        "Content-Type": "application/json",
        "x-browser-id": "32388bf0444e9a27c05474878ab23d97",
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Mobile Safari/537.36",
        "Origin": "https://pixai.art"
    }

def save_token(uid, token):
    data = {}
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, "r") as f: data = json.load(f)
        except: data = {}
    data[str(uid)] = token.replace("user_token=", "").replace("Bearer ", "").strip()
    with open(SESSION_FILE, "w") as f: json.dump(data, f)

def load_token(uid):
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, "r") as f: return json.load(f).get(str(uid))
        except: return None
    return None

def fetch_lora_meta(token, lora_id):
    params = {"operationName": "getGenerationModel", "variables": json.dumps({"id": lora_id}),
              "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": HASH_LORA}})}
    try:
        res = requests.get(API_URL, params=params, headers=get_headers(token), timeout=10).json()
        ver = res['data']['generationModel']['latestAvailableVersion']
        return {"id": ver['id'], "trigger": ver['extra'].get('triggerWords', "")}
    except: return None

def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Generate Image", "Check Credits")
    markup.add("Claim Rewards", "Fetch All Web Tasks")
    markup.add("Login / Update Token")
    return markup

# --- BOT ACTIONS ---

@bot.message_handler(commands=['start'])
def welcome(message):
    bot.send_message(message.chat.id, "PixAI Master Bot (Render Version)\nSelect an option:", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "Login / Update Token")
def login(message):
    msg = bot.send_message(message.chat.id, "Paste your user_token below:")
    bot.register_next_step_handler(msg, process_login)

def process_login(message):
    save_token(message.chat.id, message.text)
    bot.send_message(message.chat.id, "Login Successful!", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "Check Credits")
def balance(message):
    token = load_token(message.chat.id)
    if not token: return bot.send_message(message.chat.id, "Login first.")
    params = {"operationName": "listMyQuotaLogs", "variables": json.dumps({"last": 1}), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": HASH_CREDIT}})}
    try:
        res = requests.get(API_URL, params=params, headers=get_headers(token), timeout=10).json()
        bal = res['data']['me']['quotaLogs']['edges'][0]['node']['extra']['originalBalance']
        bot.send_message(message.chat.id, f"Current Balance: {bal} Credits")
    except: bot.send_message(message.chat.id, "Error: Token may be expired.")

@bot.message_handler(func=lambda m: m.text == "Claim Rewards")
def rewards(message):
    token = load_token(message.chat.id)
    if not token: return bot.send_message(message.chat.id, "Login first.")
    bot.send_message(message.chat.id, "Claiming social rewards...")
    for p in ["tiktok", "youtube", "instagram", "twitter", "discord"]:
        payload = {"operationName": "followSocialMedia", "variables": {"platform": p}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": HASH_REWARD}}}
        requests.post(API_URL, json=payload, headers=get_headers(token), timeout=10)
    bot.send_message(message.chat.id, "Reward tasks processed.")

# --- GENERATION FLOW ---

@bot.message_handler(func=lambda m: m.text == "Generate Image")
def gen_1(message):
    if not load_token(message.chat.id): return bot.send_message(message.chat.id, "Login first.")
    bot.send_message(message.chat.id, "STEP 1: Enter Prompt:")
    bot.register_next_step_handler(message, gen_2)

def gen_2(message):
    user_states[message.chat.id] = {'prompt': message.text}
    bot.send_message(message.chat.id, "STEP 2: Enter LoRA IDs (separate with space) or type 'none':")
    bot.register_next_step_handler(message, gen_3)

def gen_3(message):
    user_states[message.chat.id]['loras'] = [] if message.text.lower() == 'none' else message.text.split()
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add("1", "2", "3", "4")
    bot.send_message(message.chat.id, "STEP 3: Select Batch Size (1-4):", reply_markup=kb)
    bot.register_next_step_handler(message, gen_final)

def gen_final(message):
    uid = message.chat.id
    token = load_token(uid)
    u = user_states[uid]
    batch = int(message.text) if message.text.isdigit() else 1
    bot.send_message(uid, f"Starting Task (Batch: {batch})...", reply_markup=main_menu())
    
    l_params, l_weights, triggers = [], {}, ""
    for lid in u['loras']:
        meta = fetch_lora_meta(token, lid)
        if meta:
            l_weights[meta['id']] = 0.7
            triggers += f", {meta['trigger']}"
            l_params.append({"versionId": meta['id'], "weight": 0.7, "triggerWords": meta['trigger'], "positionInfo": {"startIndex": 0, "endIndex": 0}})

    full_prompt = u['prompt'] + triggers
    payload = {"operationName": "createGenerationTask", "variables": {"parameters": {"prompts": full_prompt, "modelId": "1861558740588989558", "width": 512, "height": 1024, "batchSize": batch, "lora": l_weights, "loraParameters": l_params, "samplingSteps": 28, "samplingMethod": "Euler a", "cfgScale": 5, "promptHelper": {"withStage": True, "userWantToEnable": True, "enable": True}}}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": HASH_GEN}}}

    try:
        res = requests.post(API_URL, json=payload, headers=get_headers(token), timeout=25).json()
        if not res or 'data' not in res: return bot.send_message(uid, "PixAI server rejected Render connection.")
        task_id = res['data']['createGenerationTask']['id']
        
        while True:
            time.sleep(12)
            poll = {"operationName": "getTaskById", "variables": json.dumps({"id": task_id}), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": HASH_POLL}})}
            s_res = requests.get(API_URL, params=poll, headers=get_headers(token), timeout=15).json()
            task = s_res['data']['task']

            if task['status'] == "completed":
                # 1-BY-1 IMAGE SENDING LOGIC
                # We fetch the urls list. If PixAI gives a grid, we try to split or just send the list
                images = task['media']['urls']
                for img in images:
                    # We only send the PUBLIC variant to avoid duplicates
                    if img['variant'] == "PUBLIC":
                        bot.send_photo(uid, img['url'])
                
                # MONOSPACE PROMPT (Easy Copy)
                bot.send_message(uid, f"Prompt:\n`{full_prompt}`", parse_mode="Markdown")
                break
            if task['status'] == "failed": break
    except Exception as e: bot.send_message(uid, f"Error: {e}")

# --- FETCH ALL ---

@bot.message_handler(func=lambda m: m.text == "Fetch All Web Tasks")
def fetch_all(message):
    uid = message.chat.id
    token = load_token(uid)
    if not token: return bot.send_message(uid, "Login first.")
    bot.send_message(uid, "Fetching history...")
    try:
        vars = {"last": 50, "parameterFields": ["extra", "prompts"]}
        params = {"operationName": "listMyTasks", "variables": json.dumps(vars), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": HASH_LIST}})}
        res = requests.get(API_URL, params=params, headers=get_headers(token), timeout=20).json()
        edges = res['data']['me']['tasks']['edges']
        
        for edge in edges:
            node = edge['node']
            if node.get('status') == "completed":
                p = node['parameters'].get('prompts', 'No prompt')
                if 'media' in node and node['media'] and 'urls' in node['media']:
                    bot.send_photo(uid, node['media']['urls'][0]['url'])
                    bot.send_message(uid, f"Prompt:\n`{p}`", parse_mode="Markdown")
                    time.sleep(1)
        bot.send_message(uid, "Fetched successfully.")
    except Exception as e: bot.send_message(uid, f"Error: {e}")

# --- START ---
if __name__ == "__main__":
    # Start web server thread for Render
    threading.Thread(target=run_web).start()
    print("Health server active.")
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
