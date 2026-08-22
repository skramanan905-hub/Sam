import json, httpx, time, uuid, random, asyncio, os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiohttp import web

# ==================== CONFIGURATION ====================
API_TOKEN = "8893616679:AAF1jHDUWj2DWmedhoThjdJbfL-BV-r4Lwk"
MY_CHAT_ID = "1827265590"
BASE_URL = "https://lasercashadmin.bonixgames.com/api"
PORT = int(os.getenv("PORT", 10000))
DATA_FILE = "laser_30_bank.json"

# ==================== DATA STORAGE ====================
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f: return json.load(f)
    return {str(i): {"token": None, "device": None, "sub": None} for i in range(1, 31)}

def save_data(data):
    with open(DATA_FILE, "w") as f: json.dump(data, f, indent=4)

USER_ACCOUNTS = load_data()
active_tasks = {}

class SetupStates(StatesGroup):
    waiting_for_bearer = State()
    waiting_for_device = State()
    waiting_for_sub = State()

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# -------------------- API HELPERS -------------------- #

def get_headers(no):
    acc = USER_ACCOUNTS[str(no)]
    return {
        "user-agent": "MyApp/1.0.7 (android)",
        "authorization": f"Bearer {acc['token']}",
        "content-type": "application/json",
        "x-request-nonce": str(uuid.uuid4()),
        "x-subscription-id": acc['sub'],
        "x-device-id": acc['device'],
        "x-request-timestamp": str(int(time.time() * 1000)),
        "x-app-version": "1.0.7",
        "x-platform": "android",
        "host": "lasercashadmin.bonixgames.com"
    }

async def send_log(msg):
    try: await bot.send_message(MY_CHAT_ID, msg, parse_mode="HTML")
    except: pass

# -------------------- EARNING MODULES -------------------- #

async def farm_gems(client, no, tag):
    while True:
        r = await client.get(f"{BASE_URL}/super-offers", headers=get_headers(no))
        if "limit" in r.text.lower() or not r.json().get("data"): break
        offer = r.json()["data"]
        if offer.get("can_unlock") or offer.get("can_earn"):
            await client.post(f"{BASE_URL}/super-offers/unlock", json={"super_offer_id": offer["id"], "timing": "0"}, headers=get_headers(no))
            await asyncio.sleep(2)
            await client.post(f"{BASE_URL}/super-offers/earn", json={"super_offer_id": offer["id"]}, headers=get_headers(no))
            await send_log(f"💰 {tag}: Super Claimed!")
        else:
            h = get_headers(no)
            await asyncio.gather(client.post(f"{BASE_URL}/v2/ad-impression", json={"provider":"admob","ad_type":"rewarded"}, headers=h),
                               client.post(f"{BASE_URL}/adx/update", json={"adx_item_id":0}, headers=h))
            await asyncio.sleep(random.randint(3, 5))
            claim = await client.post(f"{BASE_URL}/play-games/play", json={"timing": "115000", "is_ad_seen": True}, headers=h)
            if "limit" in claim.text.lower(): break
        await asyncio.sleep(1)

async def play_games(client, no, tag):
    r = await client.get(f"{BASE_URL}/games", headers=get_headers(no))
    for g in r.json().get("data", []):
        if not g.get("claimed"):
            await asyncio.sleep(8)
            await client.post(f"{BASE_URL}/games/{g['id']}/play", json={"timing": "97000", "is_ad_seen": True}, headers=get_headers(no))

async def watch_ads(client, no, tag):
    r = await client.get(f"{BASE_URL}/watch-ads", headers=get_headers(no))
    for ad in r.json().get("data", []):
        if ad.get("can_watch"):
            h = get_headers(no)
            await client.post(f"{BASE_URL}/v2/ad-impression", json={"provider":"admob","ad_type":"rewarded"}, headers=h)
            await asyncio.sleep(5)
            await client.post(f"{BASE_URL}/watch-ads/watch", json={"watch_ad_id": ad['id'], "timing": "36000", "is_ad_seen": True}, headers=h)

async def do_reads(client, no, tag):
    while True:
        st = await client.get(f"{BASE_URL}/read-earn/user-status", headers=get_headers(no))
        if not st.json().get("can_complete_more"): break
        r_t = await client.get(f"{BASE_URL}/read-earn/random-task", headers=get_headers(no))
        if r_t.json().get("status") == "success":
            task = r_t.json()["data"]
            await asyncio.sleep(125)
            p = {"task_id": task["id"], "verify_code": task["verify_code"], "timing": "130000", "is_ad_seen": True}
            await client.post(f"{BASE_URL}/read-earn/complete-task", json=p, headers=get_headers(no))
        else: break

# -------------------- DATA MODULES (WITHDRAW & HISTORY) -------------------- #

async def fetch_profile(client, no):
    r = await client.get(f"{BASE_URL}/v2/get-home-data", headers=get_headers(no))
    return r.json().get("data", {}).get("user", {})

async def get_history(client, no):
    r = await client.get(f"{BASE_URL}/withdrawal-history", headers=get_headers(no))
    items = r.json().get("data", [])
    if not items: return "❌ No History Found."
    msg = "📜 <b>History Status:</b>\n"
    for x in items[:5]:
        status = x.get("status", "unknown").upper()
        icon = "✅" if status == "PAID" else "⏳" if status == "PENDING" else "❌"
        code = x.get("redeem_code", {}).get("code", "Wait...") if x.get("redeem_code") else "Pending"
        msg += f"━━━━━━━━━━━━━━\n{icon} <b>{status}</b>\n💵 {x['withdrawal_method']['title']}\n🎫 <code>{code}</code>\n"
    return msg

async def start_withdraw(client, no, mid):
    u = await fetch_profile(client, no)
    p = {"withdrawal_method_id": mid, "payment_details": u.get("email"), "phone_number": u.get("phone_number")}
    r = await client.post(f"{BASE_URL}/withdrawal-requests", json=p, headers=get_headers(no))
    return f"✅ Request Sent: {r.json().get('message')}"

# -------------------- UI COMPONENTS -------------------- #

def get_main_menu():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🏦 ACCOUNT BANK")], [KeyboardButton(text="📦 EXPORT ALL TOKENS")]], resize_keyboard=True)

def get_bank_kb(page=1):
    btns = []
    start = (page-1)*10 + 1
    for i in range(start, start+10):
        acc = USER_ACCOUNTS[str(i)]
        icon = "⚪" if not acc['token'] else "⚡" if active_tasks.get(str(i)) else "🟢"
        btns.append(InlineKeyboardButton(text=f"{icon} Slot {i}", callback_data=f"view_{i}"))
    rows = [btns[i:i+2] for i in range(0, len(btns), 2)]
    nav = []
    if page > 1: nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"page_{page-1}"))
    if page < 3: nav.append(InlineKeyboardButton(text="➡️", callback_data=f"page_{page+1}"))
    rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)

def get_acc_kb(no):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 PROFILE", callback_data=f"prof_{no}"), InlineKeyboardButton(text="📖 HISTORY", callback_data=f"hist_{no}")],
        [InlineKeyboardButton(text="⚡ SMART ALL", callback_data=f"smart_{no}")],
        [InlineKeyboardButton(text="💎 GEMS", callback_data=f"gems_{no}"), InlineKeyboardButton(text="🎮 GAMES", callback_data=f"play_{no}")],
        [InlineKeyboardButton(text="📺 ADS", callback_data=f"ads_{no}"), InlineKeyboardButton(text="📖 READ", callback_data=f"read_{no}")],
        [InlineKeyboardButton(text="💳 ₹10", callback_data=f"draw_7_{no}"), InlineKeyboardButton(text="💳 ₹20", callback_data=f"draw_8_{no}"), InlineKeyboardButton(text="💳 ₹50", callback_data=f"draw_9_{no}")],
        [InlineKeyboardButton(text="🔧 UPDATE IDS", callback_data=f"edit_{no}")],
        [InlineKeyboardButton(text="🛑 STOP", callback_data=f"stop_{no}"), InlineKeyboardButton(text="🔙 BACK", callback_data="page_1")]
    ])

# -------------------- HANDLERS -------------------- #

@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    if str(m.chat.id) != MY_CHAT_ID: return
    await m.answer("🛰 <b>Laser Cash v1.0.7 Master Bot</b>", reply_markup=get_main_menu(), parse_mode="HTML")

@dp.message(F.text == "🏦 ACCOUNT BANK")
async def open_bank(m: types.Message):
    await m.answer("Select Slot:", reply_markup=get_bank_kb(1))

@dp.message(F.text == "📦 EXPORT ALL TOKENS")
async def export_data(m: types.Message):
    formatted = "ACCOUNTS = " + json.dumps(USER_ACCOUNTS, indent=4)
    await m.answer(f"📋 <b>Bank Backup:</b>\n\n<code>{formatted}</code>", parse_mode="HTML")

@dp.callback_query()
async def cb_handler(c: types.CallbackQuery, state: FSMContext):
    d = c.data.split("_")
    action, no = d[0], d[-1]
    
    async with httpx.AsyncClient(http2=True, verify=False) as client:
        if action == "page": await c.message.edit_reply_markup(reply_markup=get_bank_kb(int(no)))
        elif action == "view":
            acc = USER_ACCOUNTS[no]
            t_display = acc['token'][:10] + "..." if acc['token'] else "None"
            await c.message.edit_text(f"📂 <b>Slot {no}</b>\nToken: <code>{t_display}</code>", reply_markup=get_acc_kb(no), parse_mode="HTML")
        elif action == "edit":
            await state.update_data(editing_no=no)
            await c.message.answer(f"🛠 Updating Slot {no}\nSend <b>Bearer Token</b>:", reply_markup=ReplyKeyboardRemove())
            await state.set_state(SetupStates.waiting_for_bearer)
        elif action == "prof":
            u = await fetch_profile(client, no)
            await c.message.answer(f"👤 <b>{u.get('name')}</b>\n💰 Coins: {u.get('coins')}\n📧 {u.get('email')}", parse_mode="HTML")
        elif action == "hist":
            res = await get_history(client, no)
            await c.message.answer(res, parse_mode="HTML")
        elif action == "draw":
            res = await start_withdraw(client, no, d[1])
            await c.message.answer(res)
        elif action in ["smart", "gems", "play", "ads", "read"]:
            if active_tasks.get(no): return await c.answer("Running!")
            active_tasks[no] = asyncio.create_task(worker_loop(no, action))
            await c.answer("Mission Started!")
        elif action == "stop":
            if active_tasks.get(no): active_tasks[no].cancel(); active_tasks[no] = None
            await c.answer("Stopped.")

# --- FSM SETUP ---
@dp.message(SetupStates.waiting_for_bearer)
async def set_b(m: types.Message, state: FSMContext):
    await state.update_data(token=m.text.replace("Bearer ", "").strip())
    await m.answer("Send <b>Device ID</b>:")
    await state.set_state(SetupStates.waiting_for_device)

@dp.message(SetupStates.waiting_for_device)
async def set_d(m: types.Message, state: FSMContext):
    await state.update_data(device=m.text.strip())
    await m.answer("Send <b>Subscription ID</b>:")
    await state.set_state(SetupStates.waiting_for_sub)

@dp.message(SetupStates.waiting_for_sub)
async def set_s(m: types.Message, state: FSMContext):
    st = await state.get_data()
    USER_ACCOUNTS[st['editing_no']] = {"token": st['token'], "device": st['device'], "sub": m.text.strip()}
    save_data(USER_ACCOUNTS)
    await m.answer(f"✅ Slot {st['editing_no']} Saved!", reply_markup=get_main_menu())
    await state.clear()

# -------------------- MASTER WORKER -------------------- #

async def worker_loop(no, mode):
    tag = f"<b>[Slot {no}]</b>"
    async with httpx.AsyncClient(http2=True, verify=False, timeout=30) as client:
        try:
            if mode in ["smart", "gems"]: await farm_gems(client, no, tag)
            if mode in ["smart", "play"]: await play_games(client, no, tag)
            if mode in ["smart", "ads"]:  await watch_ads(client, no, tag)
            if mode in ["smart", "read"]: await do_reads(client, no, tag)
            await send_log(f"🏁 {tag} Mode [{mode}] Finished.")
        except Exception as e: await send_log(f"❌ {tag} Error: {str(e)}")
        finally: active_tasks[no] = None

async def main():
    app = web.Application(); app.router.add_get("/", lambda r: web.Response(text="OK"))
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', PORT).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
