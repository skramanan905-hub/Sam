import telebot, requests, time, json, os, threading
from flask import Flask
from telebot import types

# --- RENDER PORT FIX ---
app = Flask('')
@app.route('/')
def home(): return "PixAI Master System: 100% Online"

def run_web():
    try: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
    except: pass

# ================= CONFIGURATION =================
API_TOKEN = "8616821892:AAGvSzp-5SRGyQO4V-wcTX-YPt4j8XrZcVg"
bot = telebot.TeleBot(API_TOKEN)

SESSION_FILE, API_URL = "session.json", "https://api.pixai.art/graphql"

# Hashes from your Reqable logs
H_GEN   = "61b5dafa7ade64f847051cdca7024b359bae652421834b8f78423d7640f17d96"
H_POLL  = "a32947c6b546befddacd08a3af63cc4ee2277af27fd43342a01fc0414fca3e8a"
H_LORA  = "4e1614f7373d676cb8ec17975796188369ce321a6e78336558ec50f0c2317840"
H_ROLL  = "f0778d88963cc4e40749a8ecd9d510808b4a14cd63fac498e7763e6d5d780e5e"
H_REW   = "923002464a8e816706394061c18316cd2d14f5f025dbd1d08020e44cd8a23546"
H_CRE   = "5bd29d8deb9cfd846370a5138d99179e6b8484e176396e478d5954045cf52981"
H_LIST  = "cc067203ddd0846c19d9e247d837c32da498247ec252fe30828434f2f136f53d"
H_UPLOAD = "dd71971acde11807d01862ff1a94657479f7e833af75eac850aa2de0a14fa1fa"
H_SEARCH = "4d76952c681f7d0787077ddeec310f6475ab059e50546248120617abfb4031e9"

user_states = {}
user_search_state = {}

# --- HELPERS ---
def get_h(t): 
    return {"Authorization": f"Bearer {t.strip()}", "Content-Type": "application/json", "x-browser-id": "08df9bc9358ad97ebfe0ac86284587e5", "User-Agent": "Mozilla/5.0 (Linux; Android 15; I2301)"}

def load_t(uid):
    if os.path.exists(SESSION_FILE):
        try:
            data = json.load(open(SESSION_FILE))
            return data.get(str(uid))
        except: return None
    return None

def fetch_lora_metadata(token, lid):
    params = {"operationName": "getGenerationModel", "variables": json.dumps({"id": lid}), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_LORA}})}
    try:
        res = requests.get(API_URL, params=params, headers=get_h(token), timeout=10).json()
        v = res['data']['generationModel']['latestAvailableVersion']
        return {"id": v['id'], "trigger": v['extra'].get('triggerWords', "")}
    except: return None

def safe_send_result(uid, img_url, prompt):
    try:
        # Mono-prompt fix and caption length check
        if len(prompt) > 900:
            bot.send_photo(uid, img_url, caption="Image Ready. Full prompt below:")
            bot.send_message(uid, f"`{prompt}`", parse_mode="Markdown")
        else:
            bot.send_photo(uid, img_url, caption=f"`{prompt}`", parse_mode="Markdown")
    except:
        bot.send_message(uid, f"Link: {img_url}\n\nPrompt: `{prompt}`", parse_mode="Markdown")

def main_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.row("Generate Image", "Reference Image")
    m.row("Search LoRAs", "Auto Claim Everything")
    m.row("Check Credits", "Fetch All Web Tasks")
    m.row("Login / Update Token")
    return m

# --- HANDLERS ---

@bot.message_handler(commands=['start'])
def welcome(m):
    bot.send_message(m.chat.id, "PixAI Master Bot: All options are now fixed and integrated.", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "Login / Update Token")
def login(m):
    msg = bot.send_message(m.chat.id, "Paste your user_token below:")
    bot.register_next_step_handler(msg, process_login)

def process_login(m):
    token = m.text.replace("user_token=","").replace("Bearer ","").strip()
    data = {}
    if os.path.exists(SESSION_FILE):
        try: data = json.load(open(SESSION_FILE))
        except: data = {}
    data[str(m.chat.id)] = token
    json.dump(data, open(SESSION_FILE, "w"))
    bot.send_message(m.chat.id, "Login Successful!", reply_markup=main_menu())

# --- OPTION: SEARCH ---
@bot.message_handler(func=lambda m: m.text == "Search LoRAs")
def search_init(m):
    msg = bot.send_message(m.chat.id, "Enter keyword to search (Example: aunt):")
    bot.register_next_step_handler(msg, process_initial_search)

def process_initial_search(m):
    uid = m.chat.id
    user_search_state[uid] = {"keyword": m.text, "cursor": None, "page_num": 1}
    fetch_and_send_results(uid)

def fetch_and_send_results(uid):
    token = load_t(uid)
    state = user_search_state.get(uid)
    if not token or not state: return

    bot.send_message(uid, f"Fetching Page {state['page_num']} for '{state['keyword']}'...")
    params = {"operationName": "listGenerationModels", "variables": json.dumps({"keyword": state["keyword"], "feed": "meilisearch", "first": 8, "after": state["cursor"]}), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_SEARCH}})}
    
    try:
        res = requests.get(API_URL, params=params, headers=get_h(token), timeout=15).json()
        data = res['data']['generationModels']
        if not data['edges']: return bot.send_message(uid, "End of results reached.")

        for i, edge in enumerate(data['edges'], 1):
            node = edge['node']
            total_index = ((state['page_num'] - 1) * 8) + i
            img_url = node['coverMedia']['urls'][0]['url'] if node.get('coverMedia') else "https://pixai.art/favicon.ico"
            caption = f"#{total_index} **{node['title']}**\nID: `{node['id']}`\n\nTap ID to copy"
            bot.send_photo(uid, img_url, caption=caption, parse_mode="Markdown")
            time.sleep(0.5)

        markup = types.InlineKeyboardMarkup()
        if data['pageInfo']['hasNextPage']:
            user_search_state[uid]["cursor"] = data['pageInfo']['endCursor']
            markup.add(types.InlineKeyboardButton("Next 8 Results >>>", callback_data="next_search_page"))
        bot.send_message(uid, f"End of Page {state['page_num']}.", reply_markup=markup)
    except: bot.send_message(uid, "Search failed. Update token.")

@bot.callback_query_handler(func=lambda call: call.data == "next_search_page")
def handle_next_search(call):
    uid = call.message.chat.id
    if uid in user_search_state:
        user_search_state[uid]["page_num"] += 1
        fetch_and_send_results(uid)
        bot.answer_callback_query(call.id)

# --- OPTION: AUTO CLAIM ---
@bot.message_handler(func=lambda m: m.text == "Auto Claim Everything")
def auto_claim(m):
    token = load_t(m.chat.id)
    if not token: return bot.send_message(m.chat.id, "Login first.")
    h, rep = get_h(token), "Claim Status:\n"
    # Gacha Roll
    try:
        r_roll = requests.post(API_URL, json={"operationName": "rollAprilFools2026Lottery", "variables": {}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_ROLL}}}, headers=h).json()
        if "errors" in r_roll: rep += "- Gacha: Already rolled.\n"
        else: rep += f"- Gacha: SUCCESS (+{r_roll['data']['rollLottery']['aprilFoolsEvent2026Reward']['creditReward']})\n"
    except: pass
    # Milestones
    m_count = 0
    for t in ["tier_100k", "tier_200k", "tier_300k", "tier_400k", "tier_500k", "tier_650k", "tier_800k"]:
        try:
            if requests.post("https://api.pixai.art/v2/event/aprilFoolsEvent2026/tier-rewards/aprilFools2026CreditSpending/claim", json={"rewardTierId": t}, headers=h).json().get('success'): m_count += 1
        except: pass
    # Daily Rewards
    for p in ["tiktok", "youtube", "instagram", "twitter", "discord"]:
        requests.post(API_URL, json={"operationName": "followSocialMedia", "variables": {"platform": p}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_REW}}}, headers=h)
    rep += f"- Milestones: {m_count} claimed.\n- Daily: All social tasks synced."
    bot.send_message(m.chat.id, rep)

# --- GENERATION FLOW ---
@bot.message_handler(func=lambda m: m.text in ["Generate Image", "Reference Image"])
def gen_init(m):
    uid = m.chat.id
    if not load_t(uid): return bot.send_message(uid, "Login first.")
    user_states[uid] = {'mode': m.text}
    bot.register_next_step_handler(bot.send_message(uid, "STEP 1: Enter Prompt:"), gen_s2)

def gen_s2(m):
    user_states[m.chat.id]['prompt'] = m.text
    bot.register_next_step_handler(bot.send_message(m.chat.id, "STEP 2: LoRA IDs (or 'none'):"), gen_s3)

def gen_s3(m):
    user_states[m.chat.id]['loras'] = [] if m.text.lower() == 'none' else m.text.split()
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True); kb.add("1","2","3","4")
    bot.register_next_step_handler(bot.send_message(m.chat.id, "STEP 3: Select Batch Size:"), gen_s4)

def gen_s4(m):
    uid = m.chat.id
    user_states[uid]['batch'] = m.text
    if user_states[uid]['mode'] == "Reference Image":
        bot.send_message(uid, "STEP 4: Send the Photo now:")
    else: execute_gen(uid)

@bot.message_handler(content_types=['photo'])
def handle_photo(m):
    uid = m.chat.id
    if uid in user_states and user_states[uid].get('mode') == "Reference Image":
        bot.send_message(uid, "Uploading...")
        file_bytes = bot.download_file(bot.get_file(m.photo[-1].file_id).file_path)
        token = load_t(uid)
        try:
            res1 = requests.post(API_URL, json={"operationName": "uploadMedia", "variables": {"input": {"type": "IMAGE", "provider": "S3"}}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_UPLOAD}}}, headers=get_h(token)).json()
            up_url = res1['data']['uploadMedia']['uploadUrl']
            requests.put(up_url, data=file_bytes)
            res3 = requests.post(API_URL, json={"operationName": "uploadMedia", "variables": {"input": {"type": "IMAGE", "provider": "S3", "externalId": up_url.split('/')[-1].split('?')[0]}}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_UPLOAD}}}, headers=get_h(token)).json()
            user_states[uid]['mid'] = res3['data']['uploadMedia']['mediaId']
            bot.register_next_step_handler(bot.send_message(uid, "Photo Ready! STEP 5: Enter Strength (0.1-0.9):"), gen_final)
        except: bot.send_message(uid, "Upload failed.")

def gen_final(m):
    user_states[m.chat.id]['str'] = m.text
    execute_gen(m.chat.id)

def execute_gen(uid):
    t, u = load_t(uid), user_states[uid]
    bot.send_message(uid, "Generating Batch...", reply_markup=main_menu())
    l_ids, l_params, triggers = {}, [], ""
    for lid in u['loras']:
        meta = fetch_lora_metadata(t, lid)
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
            sr = requests.get(API_URL, params={"operationName": "getTaskById", "variables": json.dumps({"id": tid}), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_POLL}})}, headers=get_h(t)).json()
            task = sr['data']['task']
            if task['status'] == "completed":
                for img in task['media']['urls']:
                    if img['variant'] == "PUBLIC": safe_send_result(uid, img['url'], full_p)
                break
            if task['status'] == "failed": break
    except: bot.send_message(uid, "Error during generation.")

# --- OTHER TOOLS ---
@bot.message_handler(func=lambda m: m.text == "Check Credits")
def balance(m):
    t = load_t(m.chat.id)
    if not t: return
    p = {"operationName": "getMyQuota", "variables": "{}", "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_CRE}})}
    try:
        r = requests.get(API_URL, params=p, headers=get_h(t)).json()
        bot.send_message(m.chat.id, f"Balance: {r['data']['me']['quotaAmount']} Credits")
    except: bot.send_message(m.chat.id, "Error fetching credits.")

@bot.message_handler(func=lambda m: m.text == "Fetch All Web Tasks")
def fetch_all(m):
    t = load_t(m.chat.id)
    if not t: return
    v = {"last": 30, "parameterFields": ["extra", "prompts"]}
    p = {"operationName": "listMyTasks", "variables": json.dumps(v), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_LIST}})}
    try:
        r = requests.get(API_URL, params=p, headers=get_h(t)).json()
        for edge in r['data']['me']['tasks']['edges']:
            n = edge['node']
            if n['status'] == "completed":
                safe_send_result(m.chat.id, n['media']['urls'][0]['url'], n['parameters']['prompts'])
                time.sleep(1)
    except: pass

if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    bot.infinity_polling()
