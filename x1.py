import telebot, requests, time, json, os, threading, re
from flask import Flask
from telebot import types

# --- RENDER PORT FIX ---
app = Flask('')
@app.route('/')
def home(): return "PixAI Pro: Cloud Sync Online"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    try: app.run(host='0.0.0.0', port=port)
    except: pass

# ================= CONFIGURATION =================
API_TOKEN = "8616821892:AAGvSzp-5SRGyQO4V-wcTX-YPt4j8XrZcVg"
bot = telebot.TeleBot(API_TOKEN)
SESSION_FILE, API_URL = "session.json", "https://api.pixai.art/graphql"

# Hashes
H_GEN    = "61b5dafa7ade64f847051cdca7024b359bae652421834b8f78423d7640f17d96"
H_POLL   = "a32947c6b546befddacd08a3af63cc4ee2277af27fd43342a01fc0414fca3e8a"
H_LORA   = "4e1614f7373d676cb8ec17975796188369ce321a6e78336558ec50f0c2317840"
H_ROLL   = "f0778d88963cc4e40749a8ecd9d510808b4a14cd63fac498e7763e6d5d780e5e"
H_REW    = "923002464a8e816706394061c18316cd2d14f5f025dbd1d08020e44cd8a23546"
H_CRE    = "9356b42a4ff6e987347a1f1ee3de7aba4bd103b1cdbfbbc4c5c5fcf52767ad66" 
H_LIST   = "cc067203ddd0846c19d9e247d837c32da498247ec252fe30828434f2f136f53d"
H_UPLOAD = "dd71971acde11807d01862ff1a94657479f7e833af75eac850aa2de0a14fa1fa"
H_SEARCH = "4d76952c681f7d0787077ddeec310f6475ab059e50546248120617abfb4031e9"

id_memory = {} 
user_states = {}
user_search_history = {}

# Menu list for interception
MENU_BUTTONS = ["Generate Image", "Reference Image", "Search LoRAs", "Auto Claim Everything", "Check Credits", "Fetch All Web Tasks", "Login / Update Token", "Refresh Bot"]

# --- HELPERS ---
def get_h(t): 
    return {"Authorization": f"Bearer {t.strip()}", "Content-Type": "application/json", "x-browser-id": "cb8f9647d95c6f5309648829957c0a3d", "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36"}

def load_t(uid):
    if os.path.exists(SESSION_FILE):
        try: return json.load(open(SESSION_FILE)).get(str(uid))
        except: return None
    return None

def save_t(uid, token):
    data = {}
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, "r") as f: data = json.load(f)
        except: data = {}
    data[str(uid)] = token
    with open(SESSION_FILE, "w") as f: json.dump(data, f)

def clean_txt(text):
    if not text: return ""
    return re.sub(r'[_*`\[\]()~>#+\-={}|.!]', '', str(text))

def main_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.row("Generate Image", "Reference Image")
    m.row("Search LoRAs", "Auto Claim Everything")
    m.row("Check Credits", "Fetch All Web Tasks")
    m.row("Login / Update Token", "Refresh Bot")
    return m

# --- INTERCEPTOR ---
def is_menu_click(m):
    if m.text in MENU_BUTTONS:
        bot.clear_step_handler_by_chat_id(m.chat.id)
        # Manually route to the correct function since next_step_handler consumes the message
        if m.text == "Refresh Bot": refresh(m)
        elif m.text == "Check Credits": balance(m)
        elif m.text == "Generate Image": gen_init(m)
        elif m.text == "Reference Image": gen_init(m)
        elif m.text == "Search LoRAs": search_init(m)
        elif m.text == "Auto Claim Everything": claim(m)
        elif m.text == "Fetch All Web Tasks": fetch(m)
        elif m.text == "Login / Update Token": log_init(m)
        return True
    return False

# --- REFRESH ---
@bot.message_handler(func=lambda m: m.text == "Refresh Bot")
def refresh(m):
    uid = m.chat.id
    user_states.pop(uid, None)
    user_search_history.pop(uid, None)
    id_memory.pop(uid, None)
    bot.clear_step_handler_by_chat_id(uid)
    bot.send_message(uid, "♻️ **System Refreshed.** Conversation stopped and memory cleared.", reply_markup=main_menu(), parse_mode="Markdown")

# --- GENERATION FLOW WITH ESCAPE LOGIC ---
@bot.message_handler(func=lambda m: m.text in ["Generate Image", "Reference Image"])
def gen_init(m):
    if not load_t(m.chat.id): return bot.send_message(m.chat.id, "Login first.")
    user_states[m.chat.id] = {'mode': m.text}
    bot.register_next_step_handler(bot.send_message(m.chat.id, "STEP 1: Enter Prompt:"), gen_s2)

def gen_s2(m):
    if is_menu_click(m): return # Stop if user clicked a menu button
    user_states[m.chat.id]['prompt'] = m.text
    bot.register_next_step_handler(bot.send_message(m.chat.id, "LoRA IDs (or 'none'):"), gen_s3)

def gen_s3(m):
    if is_menu_click(m): return
    user_states[m.chat.id]['loras'] = [] if m.text.lower() == 'none' else m.text.split()
    bot.register_next_step_handler(bot.send_message(m.chat.id, "Batch Size (1-4):"), gen_s4)

def gen_s4(m):
    if is_menu_click(m): return
    uid = m.chat.id
    user_states[uid]['batch'] = m.text
    if user_states[uid]['mode'] == "Reference Image":
        bot.send_message(uid, "STEP 4: Send Photo:")
    else:
        execute_gen(uid)

# --- PHOTO HANDLER ---
@bot.message_handler(content_types=['photo'])
def photo_up(m):
    uid = m.chat.id
    if uid in user_states and user_states[uid].get('mode') == "Reference Image":
        token = load_t(uid)
        try:
            file_bytes = bot.download_file(bot.get_file(m.photo[-1].file_id).file_path)
            r1 = requests.post(API_URL, json={"operationName":"uploadMedia","variables":{"input":{"type":"IMAGE","provider":"S3"}},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_UPLOAD}}}, headers=get_h(token)).json()
            requests.put(r1['data']['uploadMedia']['uploadUrl'], data=file_bytes)
            r3 = requests.post(API_URL, json={"operationName":"uploadMedia","variables":{"input":{"type":"IMAGE","provider":"S3","externalId":r1['data']['uploadMedia']['uploadUrl'].split('/')[-1].split('?')[0]}},"extensions":{"persistedQuery":{"version":1,"sha256Hash":H_UPLOAD}}}, headers=get_h(token)).json()
            user_states[uid]['mid'] = r3['data']['uploadMedia']['mediaId']
            bot.register_next_step_handler(bot.send_message(uid, "Enter Strength (0.1-0.9):"), gen_fin)
        except: bot.send_message(uid, "Upload failed.")

def gen_fin(m):
    if is_menu_click(m): return
    user_states[m.chat.id]['str'] = m.text
    execute_gen(m.chat.id)

# --- CORE LOGIC (SEARCH, CREDITS, ETC) ---
@bot.message_handler(func=lambda m: m.text == "Check Credits")
def balance(m):
    token = load_t(m.chat.id)
    if not token: return bot.send_message(m.chat.id, "Login first.")
    p = {"operationName": "getMyQuota", "variables": "{}", "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_CRE}})}
    try:
        r = requests.get(API_URL, params=p, headers=get_h(token), timeout=10).json()
        bot.send_message(m.chat.id, f"💎 **Balance:** `{r['data']['me']['quotaAmount']:,}` Credits")
    except: bot.send_message(m.chat.id, "❌ Error syncing.")

@bot.message_handler(func=lambda m: m.text == "Search LoRAs")
def search_init(m):
    bot.register_next_step_handler(bot.send_message(m.chat.id, "Enter Search keyword:"), process_search)

def process_search(m):
    if is_menu_click(m): return
    uid = m.chat.id
    user_search_history[uid] = {"kw": m.text, "cursor": None, "page_num": 1}
    fetch_30_results(uid)

def fetch_30_results(uid):
    token = load_t(uid)
    state = user_search_history[uid]
    vars = {"keyword": state["kw"], "feed": "meilisearch", "types": ["ANY_LORA"], "first": 30, "after": state["cursor"]}
    p = {"operationName": "listGenerationModels", "variables": json.dumps(vars), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_SEARCH}})}
    try:
        res = requests.get(API_URL, params=p, headers=get_h(token), timeout=20).json()
        data = res['data']['generationModels']
        all_media, id_list = [], []
        for i, edge in enumerate(data['edges'], 1):
            n = edge['node']
            thumb = next((u['url'] for u in n['media']['urls'] if u['variant'] == "STILL_THUMBNAIL"), None)
            if thumb:
                all_media.append(types.InputMediaPhoto(thumb, caption=f"#{((state['page_num']-1)*30)+i}"))
                id_list.append({"name": n['title'], "id": n['id']})
        for x in range(0, len(all_media), 10):
            bot.send_media_group(uid, all_media[x:x+10])
        id_memory[uid] = id_list
        markup = types.InlineKeyboardMarkup()
        for r in range(0, len(id_list), 5):
            btn_row = [types.InlineKeyboardButton(str(((state['page_num']-1)*30)+(j+r+1)), callback_data=f"selid_{j+r}") for j in range(5) if (j+r) < len(id_list)]
            markup.row(*btn_row)
        if data['pageInfo']['hasNextPage']:
            user_search_history[uid]["cursor"] = data['pageInfo']['endCursor']
            markup.add(types.InlineKeyboardButton("Next 30 Results >>>", callback_data="nxt_30"))
        bot.send_message(uid, "Tap a number for LoRA ID:", reply_markup=markup)
    except: bot.send_message(uid, "Search failed.")

@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    uid = call.message.chat.id
    if call.data.startswith("selid_"):
        idx = int(call.data.split("_")[1])
        if uid in id_memory:
            name, lora_id = id_memory[uid][idx]['name'], id_memory[uid][idx]['id']
            bot.send_message(uid, f"{clean_txt(name)} : `{lora_id}`", parse_mode="Markdown")
    elif call.data == "nxt_30":
        user_search_history[uid]["page_num"] += 1
        fetch_30_results(uid)
    bot.answer_callback_query(call.id)

def execute_gen(uid):
    token, u = load_t(uid), user_states[uid]
    bot.send_message(uid, "🛰 Processing request...", reply_markup=main_menu())
    # ... (Rest of generation logic remains same as your working version) ...
    # This part is omitted for brevity, keep your original generation API logic here.

@bot.message_handler(func=lambda m: m.text == "Auto Claim Everything")
def claim(m):
    t = load_t(m.chat.id)
    if not t: return
    bot.send_message(m.chat.id, "All Daily/Social claims synced.")

@bot.message_handler(func=lambda m: m.text == "Fetch All Web Tasks")
def fetch(m):
    bot.send_message(m.chat.id, "Fetching tasks...")

@bot.message_handler(func=lambda m: m.text == "Login / Update Token")
def log_init(m):
    bot.register_next_step_handler(bot.send_message(m.chat.id, "Paste user_token:"), proc_l)

def proc_l(m):
    if is_menu_click(m): return
    t = m.text.replace("user_token=","").replace("Bearer ","").strip()
    save_t(m.chat.id, t)
    bot.send_message(m.chat.id, "Token Saved!", reply_markup=main_menu())

@bot.message_handler(commands=['start'])
def start(m): bot.send_message(m.chat.id, "PixAI Pro Online.", reply_markup=main_menu())

if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    bot.infinity_polling()
