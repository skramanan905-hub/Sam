import telebot, requests, time, json, os, threading, re
from flask import Flask
from telebot import types

# --- RENDER PORT BINDING ---
app = Flask('')
@app.route('/')
def home(): return "PixAI Ultimate Sync: Online"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    try: app.run(host='0.0.0.0', port=port)
    except: pass

# ================= CONFIGURATION =================
API_TOKEN = "8748542024:AAHbhNJHZP8Tdo_OLam-h6CJGMG9S5n6MDU"
bot = telebot.TeleBot(API_TOKEN)
SESSION_FILE, API_URL = "session.json", "https://api.pixai.art/graphql"

# Final Hash Database (from your Reqable logs)
H_GEN    = "61b5dafa7ade64f847051cdca7024b359bae652421834b8f78423d7640f17d96"
H_POLL   = "a32947c6b546befddacd08a3af63cc4ee2277af27fd43342a01fc0414fca3e8a"
H_LORA   = "4e1614f7373d676cb8ec17975796188369ce321a6e78336558ec50f0c2317840"
H_SEARCH = "4d76952c681f7d0787077ddeec310f6475ab059e50546248120617abfb4031e9"
H_UPLOAD = "dd71971acde11807d01862ff1a94657479f7e833af75eac850aa2de0a14fa1fa"
H_ROLL   = "f0778d88963cc4e40749a8ecd9d510808b4a14cd63fac498e7763e6d5d780e5e"
H_REW    = "923002464a8e816706394061c18316cd2d14f5f025dbd1d08020e44cd8a23546"
H_CRE    = "9356b42a4ff6e987347a1f1ee3de7aba4bd103b1cdbfbbc4c5c5fcf52767ad66"
H_LIST   = "cc067203ddd0846c19d9e247d837c32da498247ec252fe30828434f2f136f53d"

user_states = {}
user_search_history = {}
id_memory = {}

# --- CORE HELPERS ---
def get_h(t): 
    return {"Authorization": f"Bearer {t.strip()}", "Content-Type": "application/json", "x-browser-id": "08df9bc9358ad97ebfe0ac86284587e5", "User-Agent": "Mozilla/5.0 (Linux; Android 15; I2301)"}

def load_t(uid):
    if os.path.exists(SESSION_FILE):
        try: return json.load(open(SESSION_FILE)).get(str(uid))
        except: return None
    return None

def clean_txt(text):
    if not text: return ""
    return re.sub(r'[_*`\[\]()~>#+\-={}|.!]', '', str(text))

def fetch_lora_meta(token, lid):
    p = {"operationName": "getGenerationModel", "variables": json.dumps({"id": lid}), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_LORA}})}
    try:
        res = requests.get(API_URL, params=p, headers=get_h(token), timeout=10).json()
        v = res['data']['generationModel']['latestAvailableVersion']
        return {"v_id": v['id'], "trigger": v['extra'].get('triggerWords', "")}
    except: return None

def main_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.row("Generate Image", "Reference Image")
    m.row("Search LoRAs", "Auto Claim Everything")
    m.row("Check Credits", "Fetch All Web Tasks")
    m.row("Login / Update Token")
    return m

# --- OPTION: 30-RESULT ACCURATE GRID SEARCH ---
@bot.message_handler(func=lambda m: m.text == "Search LoRAs")
def search_init(m):
    bot.register_next_step_handler(bot.send_message(m.chat.id, "Enter Search keyword (30-Grid Discovery):"), start_search)

def start_search(m):
    uid = m.chat.id
    user_search_history[uid] = {"kw": m.text, "cursor": None, "page_num": 1}
    fetch_30_grid(uid)

def fetch_30_grid(uid):
    token, state = load_t(uid), user_search_history[uid]
    if not token: return bot.send_message(uid, "Login first.")
    
    bot.send_message(uid, f"Finding '{state['kw']}' - Page {state['page_num']} (30 Results)...")
    vars = {"keyword": state["kw"], "feed": "meilisearch", "types": ["ANY_LORA"], "first": 30, "after": state["cursor"]}
    p = {"operationName": "listGenerationModels", "variables": json.dumps(vars), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_SEARCH}})}

    try:
        res = requests.get(API_URL, params=p, headers=get_h(token), timeout=20).json()
        data = res['data']['generationModels']
        if not data['edges']: return bot.send_message(uid, "End of results.")

        all_media, page_ids = [], []
        for i, edge in enumerate(data['edges'], 1):
            n = edge['node']
            thumb = next((u['url'] for u in n['media']['urls'] if u['variant'] == "STILL_THUMBNAIL"), None)
            if thumb:
                total_idx = ((state['page_num'] - 1) * 30) + i
                all_media.append(types.InputMediaPhoto(thumb, caption=f"#{total_idx}"))
                page_ids.append({"name": n['title'], "id": n['id']})

        # Send 3 chunks of 10 to Telegram
        for x in range(0, len(all_media), 10):
            bot.send_media_group(uid, all_media[x:x+10])
            time.sleep(1.5)

        id_memory[uid] = page_ids
        markup = types.InlineKeyboardMarkup()
        for r in range(0, len(page_ids), 5):
            btn_row = [types.InlineKeyboardButton(str(((state['page_num']-1)*30)+(j+r+1)), callback_data=f"get_{j+r}") for j in range(5) if (j+r) < len(page_ids)]
            markup.row(*btn_row)

        if data['pageInfo']['hasNextPage']:
            user_search_history[uid]["cursor"] = data['pageInfo']['endCursor']
            markup.add(types.InlineKeyboardButton("Next 30 Results >>>", callback_data="nxt_page"))
        
        bot.send_message(uid, "Tap a number to see the ID in monospace:", reply_markup=markup)
    except: bot.send_message(uid, "Search failed. Check token.")

@bot.callback_query_handler(func=lambda call: True)
def btn_handler(call):
    uid = call.message.chat.id
    if call.data.startswith("get_"):
        idx = int(call.data.split("_")[1])
        if uid in id_memory and idx < len(id_memory[uid]):
            item = id_memory[uid][idx]
            bot.send_message(uid, f"Model: **{clean_txt(item['name'])}**\nID: `{item['id']}`", parse_mode="Markdown")
    elif call.data == "nxt_page":
        user_search_history[uid]["page_num"] += 1
        fetch_30_grid(uid)
    bot.answer_callback_query(call.id)

# --- OPTION: TRUE BALANCE SYNC ---
@bot.message_handler(func=lambda m: m.text == "Check Credits")
def balance(m):
    t = load_t(m.chat.id)
    if not t: return
    p = {"operationName":"getMyQuota","variables":"{}","extensions":json.dumps({"persistedQuery":{"version":1,"sha256Hash":H_CRE}})}
    try:
        r = requests.get(API_URL, params=p, headers=get_h(t)).json()
        bot.send_message(m.chat.id, f"💎 **Absolute Account Balance:** `{r['data']['me']['quotaAmount']:,}` Credits")
    except: bot.send_message(m.chat.id, "API Error.")

# --- OPTION: AUTO CLAIM (GACHA + MILESTONES + SOCIAL) ---
@bot.message_handler(func=lambda m: m.text == "Auto Claim Everything")
def auto_claim(m):
    t = load_t(m.chat.id)
    if not t: return
    h, rep = get_h(t), "Claim Status:\n"
    # Gacha Roll
    try:
        r = requests.post(API_URL, json={"operationName":"rollAprilFools2026Lottery","variables":{},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_ROLL}}}, headers=h).json()
        if "errors" in r: rep += "- Gacha: Already done today.\n"
        else: rep += f"- Gacha: SUCCESS (+{r['data']['rollLottery']['aprilFoolsEvent2026Reward']['creditReward']})\n"
    except: pass
    # Milestone Cashback loop (100k to 1M)
    m_count = 0
    for tier in ["tier_100k", "tier_200k", "tier_300k", "tier_400k", "tier_500k", "tier_650k", "tier_800k", "tier_1000k"]:
        try:
            if requests.post("https://api.pixai.art/v2/event/aprilFoolsEvent2026/tier-rewards/aprilFools2026CreditSpending/claim", json={"rewardTierId":tier}, headers=h).json().get('success'): m_count += 1
        except: pass
    # Social Rewards
    for p in ["tiktok", "youtube", "instagram", "twitter", "discord"]:
        requests.post(API_URL, json={"operationName":"followSocialMedia","variables":{"platform":p},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_REW}}}, headers=h)
    bot.send_message(m.chat.id, f"{rep}- Milestones: {m_count} claimed.\n- Social Rewards: Synced.")

# --- GENERATION FLOW (1-by-1 + MONOSPACE) ---
@bot.message_handler(func=lambda m: m.text in ["Generate Image", "Reference Image"])
def gen_init(m):
    if not load_t(m.chat.id): return bot.send_message(m.chat.id, "Login first.")
    user_states[m.chat.id] = {'mode': m.text}
    bot.register_next_step_handler(bot.send_message(m.chat.id, "STEP 1: Enter Prompt:"), gen_s2)
def gen_s2(m):
    user_states[m.chat.id]['prompt'] = m.text
    bot.register_next_step_handler(bot.send_message(m.chat.id, "STEP 2: LoRA IDs (or 'none'):"), gen_s3)
def gen_s3(m):
    user_states[m.chat.id]['loras'] = [] if m.text.lower() == 'none' else m.text.split()
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True); kb.add("1","2","3","4")
    bot.register_next_step_handler(bot.send_message(m.chat.id, "STEP 3: Batch Size:"), gen_s4)
def gen_s4(m):
    uid = m.chat.id
    user_states[uid]['batch'] = m.text
    if user_states[uid]['mode'] == "Reference Image": bot.send_message(uid, "STEP 4: Send the Photo now:")
    else: execute_gen(uid)

@bot.message_handler(content_types=['photo'])
def handle_photo(m):
    uid = m.chat.id
    if uid in user_states and user_states[uid].get('mode') == "Reference Image":
        bot.send_message(uid, "Uploading...")
        file_bytes = bot.download_file(bot.get_file(m.photo[-1].file_id).file_path)
        token = load_t(uid)
        try:
            r1 = requests.post(API_URL, json={"operationName":"uploadMedia","variables":{"input":{"type":"IMAGE","provider":"S3"}},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_UPLOAD}}}, headers=get_h(token)).json()
            requests.put(r1['data']['uploadMedia']['uploadUrl'], data=file_bytes)
            r3 = requests.post(API_URL, json={"operationName":"uploadMedia","variables":{"input":{"type":"IMAGE","provider":"S3","externalId":r1['data']['uploadMedia']['uploadUrl'].split('/')[-1].split('?')[0]}},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_UPLOAD}}}, headers=get_h(token)).json()
            user_states[uid]['mid'] = r3['data']['uploadMedia']['mediaId']
            bot.register_next_step_handler(bot.send_message(uid, "STEP 5: Enter Strength (0.1-0.9):"), gen_final)
        except: bot.send_message(uid, "Upload failed.")
def gen_final(m):
    user_states[m.chat.id]['str'] = m.text
    execute_gen(m.chat.id)

def execute_gen(uid):
    token, u = load_t(uid), user_states[uid]
    bot.send_message(uid, "🛰 Processing...", reply_markup=main_menu())
    weights, params, triggers = {}, [], ""
    for lid in u['loras']:
        meta = fetch_lora_meta(token, lid)
        if meta:
            weights[meta['v_id']] = 0.7; triggers += f", {meta['trigger']}"
            params.append({"versionId": meta['v_id'], "weight": 0.7, "triggerWords": meta['trigger'], "positionInfo": {"startIndex": 0, "endIndex": 0}})
    
    full_p = u['prompt'] + triggers
    payload = {"operationName": "createGenerationTask", "variables": {"parameters": {"prompts": full_p, "modelId": "1861558740588989558", "width": 512, "height": 1024, "batchSize": int(u['batch']), "lora": weights, "loraParameters": params, "mediaId": u.get('mid'), "strength": float(u.get('str', 0.55)), "samplingSteps": 28, "samplingMethod": "Euler a", "cfgScale": 5, "promptHelper": {"withStage": True, "userWantToEnable": True, "enable": True}}}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_GEN}}}
    try:
        res = requests.post(API_URL, json=payload, headers=get_h(token), timeout=25).json()
        tid = res['data']['createGenerationTask']['id']
        while True:
            time.sleep(15)
            sr = requests.get(API_URL, params={"operationName":"getTaskById","variables":json.dumps({"id":tid}),"extensions":json.dumps({"persistedQuery":{"version":1,"sha256Hash":H_POLL}})}, headers=get_h(token)).json()
            task = sr['data']['task']
            if task['status'] == "completed":
                for img in task['media']['urls']:
                    if img['variant'] == "PUBLIC": bot.send_photo(uid, img['url'])
                bot.send_message(uid, f"`{clean_txt(full_p)}`", parse_mode="Markdown")
                break
            if task['status'] == "failed": break
    except: bot.send_message(uid, "Task Error.")

# --- UTILS: HISTORY / LOGIN ---
@bot.message_handler(func=lambda m: m.text == "Fetch All Web Tasks")
def fetch_tasks(m):
    t, uid = load_t(m.chat.id), m.chat.id
    r = requests.get(API_URL, params={"operationName":"listMyTasks","variables":json.dumps({"last":30,"parameterFields":["extra","prompts"]}),"extensions":json.dumps({"persistedQuery":{"version":1,"sha256Hash":H_LIST}})}, headers=get_h(t)).json()
    for edge in r['data']['me']['tasks']['edges']:
        if edge['node']['status'] == "completed":
            bot.send_photo(uid, edge['node']['media']['urls'][0]['url'], caption=f"`{clean_txt(edge['node']['parameters']['prompts'][:900])}`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "Login / Update Token")
def log_start(m): bot.register_next_step_handler(bot.send_message(m.chat.id, "Paste user_token:"), proc_l)
def proc_l(m):
    t = m.text.replace("user_token=","").replace("Bearer ","").strip()
    data = json.load(open(SESSION_FILE)) if os.path.exists(SESSION_FILE) else {}
    data[str(m.chat.id)] = t
    json.dump(data, open(SESSION_FILE, "w"))
    bot.send_message(m.chat.id, "Success!", reply_markup=main_menu())

@bot.message_handler(commands=['start'])
def start(m): bot.send_message(m.chat.id, "System Online. Account Synced.", reply_markup=main_menu())

if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    bot.infinity_polling()
