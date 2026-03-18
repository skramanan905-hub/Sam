import telebot, requests, time, json, os, threading
from flask import Flask
from telebot import types

# --- RENDER PORT BINDING ---
app = Flask('')
@app.route('/')
def home(): return "PixAI Bot Status: 100% Online"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# ================= CONFIGURATION =================
API_TOKEN = "8560409798:AAF_bcLa-g9W_XglVTBV2wWdOzau1cyrH_E"
bot = telebot.TeleBot(API_TOKEN)

SESSION_FILE, API_URL = "session.json", "https://api.pixai.art/graphql"

# Stored Hashes from your captured data (V6)
H_GEN   = "c057ef74858702d0205b68aa2c7701ac9d7882e288c9b01e3689e21757aef1f7"
H_POLL  = "6db0f9052ef7c760025083d34defa39cbc301029a89a893437a0da22171f74b8"
H_LORA  = "2f246fd8c1b73ed398eb4ccce2cfe08d0d502efb72ac08ad9a30e0a6ea17c090"
H_UPLOAD = "dd71971acde11807d01862ff1a94657479f7e8338f75eac850aa2de0a14fa1fa"
H_LIST  = "cc067203ddd0846c19d9e247d837c32da498247ec252fe30828434f2f136f53d"
H_CRE   = "9356b42a4ff6e987347a1f1ee3de7aba4bd103b1cdbfbbc4c5c5fcf52767ad66"
H_REW   = "923002464a8e816706394061c18316cd2d14f5f025dbd1d08020e44cd8a23546"

user_states = {}

# --- HELPERS ---
def get_h(t): 
    return {"Authorization": f"Bearer {t.strip()}", "Content-Type": "application/json", "x-browser-id": "cb8f9647d95c6f5309648829957c0a3d", "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36"}

def load_t(uid):
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, "r") as f: return json.load(f).get(str(uid))
        except: return None
    return None

def fetch_l(token, lid):
    p = {"operationName": "getGenerationModel", "variables": json.dumps({"id": lid}), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_LORA}})}
    try:
        r = requests.get(API_URL, params=p, headers=get_h(token)).json()
        v = r['data']['generationModel']['latestAvailableVersion']
        return {"id": v['id'], "trigger": v['extra'].get('triggerWords', "")}
    except: return None

def upload_to_pixai(token, file_content):
    """Automated S3 Upload logic from your logs"""
    p1 = {"operationName": "uploadMedia", "variables": {"input": {"type": "IMAGE", "provider": "S3"}}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_UPLOAD}}}
    res1 = requests.post(API_URL, json=p1, headers=get_h(token)).json()
    up_url = res1['data']['uploadMedia']['uploadUrl']
    requests.put(up_url, data=file_content, headers={"Content-Type": "application/x-www-form-urlencoded"})
    p3 = {"operationName": "uploadMedia", "variables": {"input": {"type": "IMAGE", "provider": "S3", "externalId": up_url.split('/')[-1].split('?')[0]}}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_UPLOAD}}}
    return requests.post(API_URL, json=p3, headers=get_h(token)).json()['data']['uploadMedia']['mediaId']

def menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.row("Generate Image", "Reference Image")
    m.row("Check Credits", "Claim Rewards")
    m.row("Fetch All Web Tasks", "Login / Update Token")
    return m

# --- HANDLERS ---
@bot.message_handler(commands=['start'])
def welcome(m): bot.send_message(m.chat.id, "PixAI Master System Online.", reply_markup=menu())

@bot.message_handler(func=lambda m: m.text == "Login / Update Token")
def login(m): bot.register_next_step_handler(bot.send_message(m.chat.id, "Paste user_token:"), process_login)

def process_login(m):
    t = m.text.replace("user_token=","").replace("Bearer ","").strip()
    data = json.load(open(SESSION_FILE)) if os.path.exists(SESSION_FILE) else {}
    data[str(m.chat.id)] = t
    json.dump(data, open(SESSION_FILE, "w"))
    bot.send_message(m.chat.id, "Login Success!", reply_markup=menu())

# --- GENERATION FLOW ---
@bot.message_handler(func=lambda m: m.text in ["Generate Image", "Reference Image"])
def gen_init(m):
    if not load_t(m.chat.id): return bot.send_message(m.chat.id, "Login first.")
    user_states[m.chat.id] = {'mode': m.text}
    bot.register_next_step_handler(bot.send_message(m.chat.id, "STEP 1: Enter Prompt:"), gen_step2)

def gen_step2(m):
    user_states[m.chat.id]['prompt'] = m.text
    bot.register_next_step_handler(bot.send_message(m.chat.id, "STEP 2: Enter LoRA IDs or 'none':"), gen_step3)

def gen_step3(m):
    user_states[m.chat.id]['loras'] = [] if m.text.lower() == 'none' else m.text.split()
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True); kb.add("1","2","3","4")
    bot.register_next_step_handler(bot.send_message(m.chat.id, "STEP 3: Select Batch Size:"), gen_step4)

def gen_step4(m):
    uid = m.chat.id
    user_states[uid]['batch'] = m.text
    if user_states[uid]['mode'] == "Reference Image":
        bot.send_message(uid, "STEP 4: Now send the Photo you want to use:")
    else: execute_gen(uid)

@bot.message_handler(content_types=['photo'])
def handle_photo(m):
    uid = m.chat.id
    if uid in user_states and user_states[uid].get('mode') == "Reference Image":
        bot.send_message(uid, "Uploading to PixAI...")
        f_info = bot.get_file(m.photo[-1].file_id)
        mid = upload_to_pixai(load_t(uid), bot.download_file(f_info.file_path))
        user_states[uid]['mid'] = mid
        bot.register_next_step_handler(bot.send_message(uid, "STEP 5: Enter Strength (0.1-0.9):"), gen_final)

def gen_final(m):
    user_states[m.chat.id]['str'] = m.text
    execute_gen(m.chat.id)

def execute_gen(uid):
    t, u = load_t(uid), user_states[uid]
    bot.send_message(uid, "Processing...", reply_markup=menu())
    l_ids, l_params, triggers = {}, [], ""
    for lid in u['loras']:
        meta = fetch_l(t, lid)
        if meta:
            l_ids[meta['id']] = 0.7; triggers += f", {meta['trigger']}"
            l_params.append({"versionId": meta['id'], "weight": 0.7, "triggerWords": meta['trigger'], "positionInfo": {"startIndex": 0, "endIndex": 0}})
    
    fp = u['prompt'] + triggers
    payload = {"operationName": "createGenerationTask", "variables": {"parameters": {"prompts": fp, "modelId": "1861558740588989558", "width": 512, "height": 1024, "batchSize": int(u['batch']), "lora": l_ids, "loraParameters": l_params, "mediaId": u.get('mid'), "strength": float(u.get('str', 0.55)), "samplingSteps": 28, "samplingMethod": "Euler a", "cfgScale": 5, "promptHelper": {"withStage": True, "userWantToEnable": True, "enable": True}}}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_GEN}}}
    
    try:
        res = requests.post(API_URL, json=payload, headers=get_h(t)).json()
        if not res or 'data' not in res: return bot.send_message(uid, "PixAI Busy or Render IP Blocked.")
        tid = res['data']['createGenerationTask']['id']
        while True:
            time.sleep(15)
            sr = requests.get(API_URL, params={"operationName": "getTaskById", "variables": json.dumps({"id": tid}), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_POLL}})}, headers=get_h(t)).json()
            task = sr['data']['task']
            if task['status'] == "completed":
                for img in task['media']['urls']:
                    if img['variant'] == "PUBLIC": bot.send_photo(uid, img['url'])
                bot.send_message(uid, f"`{fp}`", parse_mode="Markdown")
                break
            if task['status'] == "failed": break
    except: bot.send_message(uid, "Error creating task.")

# --- OTHER TOOLS ---
@bot.message_handler(func=lambda m: m.text == "Check Credits")
def balance(m):
    t = load_t(m.chat.id)
    r = requests.get(API_URL, params={"operationName": "getMyQuota", "variables": "{}", "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_CRE}})}, headers=get_h(t)).json()
    bot.send_message(m.chat.id, f"Balance: {r['data']['me']['quotaAmount']} Credits")

@bot.message_handler(func=lambda m: m.text == "Claim Rewards")
def claim(m):
    t = load_t(m.chat.id)
    bot.send_message(m.chat.id, "Claiming...")
    for p in ["tiktok", "youtube", "instagram", "twitter", "discord"]:
        requests.post(API_URL, json={"operationName": "followSocialMedia", "variables": {"platform": p}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_REW}}}, headers=get_h(t))
    bot.send_message(m.chat.id, "Rewards Processed.")

@bot.message_handler(func=lambda m: m.text == "Fetch All Web Tasks")
def fetch_all(m):
    t = load_t(m.chat.id)
    r = requests.get(API_URL, params={"operationName": "listMyTasks", "variables": json.dumps({"last": 50, "parameterFields": ["extra", "prompts"]}), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_LIST}})}, headers=get_h(t)).json()
    for edge in r['data']['me']['tasks']['edges']:
        n = edge['node']
        if n['status'] == "completed":
            bot.send_photo(m.chat.id, n['media']['urls'][0]['url'])
            bot.send_message(m.chat.id, f"`{n['parameters']['prompts']}`", parse_mode="Markdown")
            time.sleep(2)

if __name__ == "__main__":
    threading.Thread(target=run_web).start() # Keep-alive for Render
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
