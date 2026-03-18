import telebot, requests, time, json, os, threading
from flask import Flask
from telebot import types

# --- RENDER ALIVE SYSTEM ---
app = Flask('')
@app.route('/')
def home(): return "PixAI Bot is Online"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# ================= CONFIGURATION =================
API_TOKEN = "8560409798:AAF_bcLa-g9W_XglVTBV2wWdOzau1cyrH_E"
bot = telebot.TeleBot(API_TOKEN)

SESSION_FILE = "session.json"
API_URL = "https://api.pixai.art/graphql"

# Hashes from your Reqable logs
H_GEN    = "c057ef74858702d0205b68aa2c7701ac9d7882e288c9b01e3689e21757aef1f7"
H_POLL   = "6db0f9052ef7c760025083d34defa39cbc301029a89a893437a0da22171f74b8"
H_LORA   = "2f246fd8c1b73ed398eb4ccce2cfe08d0d502efb72ac08ad9a30e0a6ea17c090"
H_UPLOAD = "dd71971acde11807d01862ff1a94657479f7e833af75eac850aa2de0a14fa1fa"
H_LIST   = "cc067203ddd0846c19d9e247d837c32da498247ec252fe30828434f2f136f53d"
H_CRE    = "9356b42a4ff6e987347a1f1ee3de7aba4bd103b1cdbfbbc4c5c5fcf52767ad66"
H_REW    = "923002464a8e816706394061c18316cd2d14f5f025dbd1d08020e44cd8a23546"

user_states = {}

# --- HELPERS ---
def get_h(t): 
    return {"Authorization": f"Bearer {t.strip()}", "Content-Type": "application/json", "x-browser-id": "cb8f9647d95c6f5309648829957c0a3d", "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36"}

def load_t(uid):
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, "r") as f: return json.load(f).get(str(uid))
    return None

def fetch_lora(token, lid):
    p = {"operationName": "getGenerationModel", "variables": json.dumps({"id": lid}), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_LORA}})}
    try:
        r = requests.get(API_URL, params=p, headers=get_h(token)).json()
        v = r['data']['generationModel']['latestAvailableVersion']
        return {"id": v['id'], "trigger": v['extra'].get('triggerWords', "")}
    except: return None

def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("Generate Image", "Reference Image")
    markup.row("Check Credits", "Claim Rewards")
    markup.row("Fetch All Web Tasks", "Login / Update Token")
    return markup

# --- AUTO UPLOAD LOGIC ---
def upload_to_pixai(token, file_content):
    try:
        p1 = {"operationName": "uploadMedia", "variables": {"input": {"type": "IMAGE", "provider": "S3"}}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_UPLOAD}}}
        res1 = requests.post(API_URL, json=p1, headers=get_h(token)).json()
        upload_url = res1['data']['uploadMedia']['uploadUrl']
        requests.put(upload_url, data=file_content, headers={"Content-Type": "application/x-www-form-urlencoded"})
        p3 = {"operationName": "uploadMedia", "variables": {"input": {"type": "IMAGE", "provider": "S3", "externalId": upload_url.split('/')[-1].split('?')[0]}}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_UPLOAD}}}
        res3 = requests.post(API_URL, json=p3, headers=get_h(token)).json()
        return res3['data']['uploadMedia']['mediaId']
    except: return None

# --- HANDLERS ---
@bot.message_handler(commands=['start'])
def welcome(message): bot.send_message(message.chat.id, "PixAI Master Bot Ready on Render Host.", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "Login / Update Token")
def login(m): bot.register_next_step_handler(bot.send_message(m.chat.id, "Paste user_token:"), process_login)

def process_login(m):
    t = m.text.replace("user_token=","").replace("Bearer ","").strip()
    data = json.load(open(SESSION_FILE)) if os.path.exists(SESSION_FILE) else {}
    data[str(m.chat.id)] = t
    json.dump(data, open(SESSION_FILE, "w"))
    bot.send_message(m.chat.id, "Login Successful!", reply_markup=main_menu())

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
        bot.send_message(uid, "STEP 4: Now send me the Reference Photo:")
    else:
        execute_gen(uid)

@bot.message_handler(content_types=['photo'])
def handle_photo(m):
    uid = m.chat.id
    if uid in user_states and user_states[uid].get('mode') == "Reference Image":
        status = bot.send_message(uid, "Uploading photo to PixAI...")
        file_info = bot.get_file(m.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        token = load_t(uid)
        mid = upload_to_pixai(token, downloaded_file)
        if mid:
            user_states[uid]['mid'] = mid
            bot.register_next_step_handler(bot.send_message(uid, "STEP 5: Enter Strength (0.1 to 0.9):"), gen_final)
        else: bot.send_message(uid, "Upload failed.")

def gen_final(m):
    user_states[m.chat.id]['str'] = m.text
    execute_gen(m.chat.id)

def execute_gen(uid):
    t, u = load_t(uid), user_states[uid]
    bot.send_message(uid, "Requesting PixAI Engine...", reply_markup=main_menu())
    l_ids, l_params, triggers = {}, [], ""
    for lid in u['loras']:
        meta = fetch_lora(t, lid)
        if meta:
            l_ids[meta['id']] = 0.7; triggers += f", {meta['trigger']}"
            l_params.append({"versionId": meta['id'], "weight": 0.7, "triggerWords": meta['trigger'], "positionInfo": {"startIndex": 0, "endIndex": 0}})
    
    full_p = u['prompt'] + triggers
    payload = {"operationName": "createGenerationTask", "variables": {"parameters": {"prompts": full_p, "modelId": "1861558740588989558", "width": 512, "height": 1024, "batchSize": int(u['batch']), "lora": l_ids, "loraParameters": l_params, "mediaId": u.get('mid'), "strength": float(u.get('str', 0.55)), "samplingSteps": 28, "samplingMethod": "Euler a", "cfgScale": 5, "promptHelper": {"withStage": True, "userWantToEnable": True, "enable": True}}}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_GEN}}}
    
    try:
        res = requests.post(API_URL, json=payload, headers=get_h(t)).json()
        tid = res['data']['createGenerationTask']['id']
        while True:
            time.sleep(12)
            poll = {"operationName": "getTaskById", "variables": json.dumps({"id": tid}), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_POLL}})}
            sr = requests.get(API_URL, params=poll, headers=get_h(t)).json()
            task = sr['data']['task']
            if task['status'] == "completed":
                for img in task['media']['urls']:
                    if img['variant'] == "PUBLIC": bot.send_photo(uid, img['url'])
                bot.send_message(uid, f"`{full_p}`", parse_mode="Markdown")
                break
            if task['status'] == "failed": break
    except: bot.send_message(uid, "Task Error.")

# --- OTHER TOOLS ---
@bot.message_handler(func=lambda m: m.text == "Check Credits")
def balance(m):
    t = load_t(m.chat.id)
    if not t: return
    p = {"operationName": "getMyQuota", "variables": "{}", "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_CRE}})}
    try:
        r = requests.get(API_URL, params=p, headers=get_h(t)).json()
        bot.send_message(m.chat.id, f"Balance: {r['data']['me']['quotaAmount']} Credits")
    except: bot.send_message(m.chat.id, "API Error.")

@bot.message_handler(func=lambda m: m.text == "Fetch All Web Tasks")
def fetch_all(m):
    t = load_t(m.chat.id)
    v = {"last": 50, "parameterFields": ["extra", "prompts"]}
    p = {"operationName": "listMyTasks", "variables": json.dumps(v), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_LIST}})}
    r = requests.get(API_URL, params=p, headers=get_h(t)).json()
    for edge in r['data']['me']['tasks']['edges']:
        n = edge['node']
        if n['status'] == "completed":
            bot.send_photo(m.chat.id, n['media']['urls'][0]['url'])
            bot.send_message(m.chat.id, f"`{n['parameters']['prompts']}`", parse_mode="Markdown")
            time.sleep(1)

if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    bot.infinity_polling()
