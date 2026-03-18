import telebot, requests, time, json, os, threading
from flask import Flask
from telebot import types

# --- RENDER PORT BINDING (Required for Render Hosting) ---
app = Flask('')
@app.route('/')
def home(): return "PixAI Bot is Online"

def run_web():
    try: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
    except: pass

# ================= CONFIGURATION =================
# YOUR NEW TOKEN
API_TOKEN = "8748542024:AAHbhNJHZP8Tdo_OLam-h6CJGMG9S5n6MDU"
bot = telebot.TeleBot(API_TOKEN)

SESSION_FILE, API_URL = "session.json", "https://api.pixai.art/graphql"

# Static Hashes from your data logs
H_GEN   = "61b5dafa7ade64f847051cdca7024b359bae652421834b8f78423d7640f17d96"
H_POLL  = "a32947c6b546befddacd08a3af63cc4ee2277af27fd43342a01fc0414fca3e8a"
H_LORA  = "4e1614f7373d676cb8ec17975796188369ce321a6e78336558ec50f0c2317840"
H_ROLL  = "f0778d88963cc4e40749a8ecd9d510808b4a14cd63fac498e7763e6d5d780e5e"
H_REW   = "923002464a8e816706394061c18316cd2d14f5f025dbd1d08020e44cd8a23546"
H_CRE   = "5bd29d8deb9cfd846370a5138d99179e6b8484e176396e478d5954045cf52981"
H_LIST  = "cc067203ddd0846c19d9e247d837c32da498247ec252fe30828434f2f136f53d"
H_UPLOAD = "dd71971acde11807d01862ff1a94657479f7e833af75eac850aa2de0a14fa1fa"

user_states = {}

# --- HELPERS ---
def get_h(t): 
    return {"Authorization": f"Bearer {t.strip()}", "Content-Type": "application/json", "x-browser-id": "08df9bc9358ad97ebfe0ac86284587e5", "User-Agent": "Mozilla/5.0 (Linux; Android 15; I2301)"}

def load_t(uid):
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, "r") as f: return json.load(f).get(str(uid))
        except: return None
    return None

def fetch_lora(token, lid):
    p = {"operationName": "getGenerationModel", "variables": json.dumps({"id": lid}), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_LORA}})}
    try:
        r = requests.get(API_URL, params=p, headers=get_h(token), timeout=10).json()
        v = r['data']['generationModel']['latestAvailableVersion']
        return {"id": v['id'], "trigger": v['extra'].get('triggerWords', "")}
    except: return None

def main_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.row("Generate Image", "Reference Image")
    m.row("Auto Claim Everything", "Check Credits")
    m.row("Fetch All Web Tasks", "Login / Update Token")
    return m

# --- AUTO CLAIM SYSTEM (GACHA + MILESTONES + DAILY) ---
def run_auto_claim(uid, token):
    h = get_h(token)
    report = "🤖 ALL-IN-ONE CLAIM REPORT:\n\n"
    
    # 1. Roll Fortune
    try:
        p_roll = {"operationName": "rollAprilFools2026Lottery", "variables": {}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_ROLL}}}
        r_roll = requests.post(API_URL, json=p_roll, headers=h, timeout=10).json()
        if "errors" in r_roll: report += "- Gacha: Already rolled today.\n"
        else:
            rew = r_roll['data']['rollLottery']['aprilFoolsEvent2026Reward']
            report += f"- Gacha: SUCCESS! (+{rew['creditReward']} Credits)\n"
    except: report += "- Gacha: Request Timeout.\n"

    # 2. Claim Milestones
    tiers = ["tier_100k", "tier_200k", "tier_300k", "tier_400k", "tier_500k", "tier_650k", "tier_800k", "tier_900k", "tier_1000k"]
    m_count = 0
    for t in tiers:
        url = "https://api.pixai.art/v2/event/aprilFoolsEvent2026/tier-rewards/aprilFools2026CreditSpending/claim"
        try:
            res = requests.post(url, json={"rewardTierId": t}, headers=h, timeout=5).json()
            if res.get('success'): m_count += 1
        except: pass
    report += f"- Milestones: Claimed {m_count} new rewards.\n"

    # 3. Standard Daily
    for p in ["tiktok", "youtube", "instagram", "twitter", "discord"]:
        p_rew = {"operationName": "followSocialMedia", "variables": {"platform": p}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_REW}}}
        requests.post(API_URL, json=p_rew, headers=h, timeout=5)
    report += "- Daily Social: All tasks checked.\n"
    
    bot.send_message(uid, report)

# --- BOT HANDLERS ---
@bot.message_handler(commands=['start'])
def welcome(m): bot.send_message(m.chat.id, "PixAI Master Console Ready.", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "Auto Claim Everything")
def handle_auto(m):
    t = load_t(m.chat.id)
    if not t: return bot.send_message(m.chat.id, "Please Login first.")
    bot.send_message(m.chat.id, "Running all automated claims...")
    run_auto_claim(m.chat.id, t)

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
    bot.register_next_step_handler(bot.send_message(m.chat.id, "STEP 1: Enter Prompt:"), gen_s2)

def gen_s2(m):
    user_states[m.chat.id]['prompt'] = m.text
    bot.register_next_step_handler(bot.send_message(m.chat.id, "STEP 2: Enter LoRA IDs or 'none':"), gen_s3)

def gen_s3(m):
    user_states[m.chat.id]['loras'] = [] if m.text.lower() == 'none' else m.text.split()
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True); kb.add("1","2","3","4")
    bot.register_next_step_handler(bot.send_message(m.chat.id, "STEP 3: Select Batch Size:"), gen_s4)

def gen_s4(m):
    uid = m.chat.id
    user_states[uid]['batch'] = m.text
    if user_states[uid]['mode'] == "Reference Image":
        bot.send_message(uid, "STEP 4: Send the photo to use as reference:")
    else: execute_gen(uid)

@bot.message_handler(content_types=['photo'])
def handle_photo(m):
    uid = m.chat.id
    if uid in user_states and user_states[uid].get('mode') == "Reference Image":
        bot.send_message(uid, "Processing photo upload...")
        file_bytes = bot.download_file(bot.get_file(m.photo[-1].file_id).file_path)
        token = load_t(uid)
        try:
            # 3-Step Upload Logic from your data
            p1 = {"operationName": "uploadMedia", "variables": {"input": {"type": "IMAGE", "provider": "S3"}}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_UPLOAD}}}
            res1 = requests.post(API_URL, json=p1, headers=get_h(token)).json()
            up_url = res1['data']['uploadMedia']['uploadUrl']
            requests.put(up_url, data=file_bytes)
            p3 = {"operationName": "uploadMedia", "variables": {"input": {"type": "IMAGE", "provider": "S3", "externalId": up_url.split('/')[-1].split('?')[0]}}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_UPLOAD}}}
            res3 = requests.post(API_URL, json=p3, headers=get_h(token)).json()
            user_states[uid]['mid'] = res3['data']['uploadMedia']['mediaId']
            bot.register_next_step_handler(bot.send_message(uid, "Photo Ready! STEP 5: Enter Strength (0.1-0.9):"), gen_final)
        except: bot.send_message(uid, "Upload failed.")

def gen_final(m):
    user_states[m.chat.id]['str'] = m.text
    execute_gen(m.chat.id)

def execute_gen(uid):
    t, u = load_t(uid), user_states[uid]
    bot.send_message(uid, "Requesting PixAI...", reply_markup=main_menu())
    l_ids, l_params, triggers = {}, [], ""
    for lid in u['loras']:
        meta = fetch_lora(t, lid)
        if meta:
            l_ids[meta['id']] = 0.7; triggers += f", {meta['trigger']}"
            l_params.append({"versionId": meta['id'], "weight": 0.7, "triggerWords": meta['trigger'], "positionInfo": {"startIndex": 0, "endIndex": 0}})
    
    full_p = u['prompt'] + triggers
    payload = {"operationName": "createGenerationTask", "variables": {"parameters": {"prompts": full_p, "modelId": "1861558740588989558", "width": 512, "height": 1024, "batchSize": int(u['batch']), "lora": l_ids, "loraParameters": l_params, "mediaId": u.get('mid'), "strength": float(u.get('str', 0.55)), "samplingSteps": 28, "samplingMethod": "Euler a", "cfgScale": 5}}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_GEN}}}
    
    try:
        res = requests.post(API_URL, json=payload, headers=get_h(t)).json()
        tid = res['data']['createGenerationTask']['id']
        while True:
            time.sleep(15)
            poll = {"operationName": "getTaskById", "variables": json.dumps({"id": tid}), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_POLL}})}
            sr = requests.get(API_URL, params=poll, headers=get_h(t)).json()
            task = sr['data']['task']
            if task['status'] == "completed":
                # Send 1-by-1
                for img in task['media']['urls']:
                    if img['variant'] == "PUBLIC": bot.send_photo(uid, img['url'])
                # Send MONO prompt
                bot.send_message(uid, f"`{full_p}`", parse_mode="Markdown")
                break
            if task['status'] == "failed": break
    except: bot.send_message(uid, "Error.")

@bot.message_handler(func=lambda m: m.text == "Check Credits")
def balance(m):
    t = load_t(m.chat.id)
    p = {"operationName": "listMyQuotaLogs", "variables": json.dumps({"last": 1}), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_CRE}})}
    r = requests.get(API_URL, params=p, headers=get_h(t)).json()
    b = r['data']['me']['quotaLogs']['edges'][0]['node']['extra']['originalBalance']
    bot.send_message(m.chat.id, f"Balance: {b} Credits")

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
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
