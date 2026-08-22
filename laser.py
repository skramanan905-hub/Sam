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
DATA_FILE = "laser_bank.json"

# ==================== DATA PERSISTENCE ====================
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f: return json.load(f)
    return {str(i): {"token": None, "device": None, "sub": None} for i in range(1, 31)}

def save_data(data):
    with open(DATA_FILE, "w") as f: json.dump(data, f, indent=4)

USER_ACCOUNTS = load_data()
active_tasks = {}

# ==================== FSM STATES ====================
class SetupStates(StatesGroup):
    waiting_for_bearer = State()
    waiting_for_device = State()
    waiting_for_sub = State()

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# -------------------- API HELPERS -------------------- #

def get_headers(acc_no):
    acc = USER_ACCOUNTS[str(acc_no)]
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

# -------------------- EARNING MODULES (v1.0.7) -------------------- #

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
        await asyncio.sleep(2)

async def play_games(client, no, tag):
    r = await client.get(f"{BASE_URL}/games", headers=get_headers(no))
    for g in r.json().get("data", []):
        if not g.get("claimed"):
            await asyncio.sleep(8)
            await client.post(f"{BASE_URL}/games/{g['id']}/play", json={"timing": "97000", "is_ad_seen": True}, headers=get_headers(no))

# -------------------- UI LOGIC -------------------- #

def get_main_menu():
    kb = [[KeyboardButton(text="🏦 ACCOUNT BANK")], [KeyboardButton(text="📦 EXPORT ALL TOKENS")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_bank_kb(page=1):
    btns = []
    start = (page-1)*10 + 1
    for i in range(start, start+10):
        data = USER_ACCOUNTS[str(i)]
        icon = "🟢" if data['token'] else "⚪"
        if str(i) in active_tasks and active_tasks[str(i)]: icon = "⚡"
        btns.append(InlineKeyboardButton(text=f"{icon} Acc {i}", callback_data=f"view_{i}"))
    rows = [btns[i:i+2] for i in range(0, len(btns), 2)]
    nav = []
    if page > 1: nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"page_{page-1}"))
    if page < 3: nav.append(InlineKeyboardButton(text="➡️", callback_data=f"page_{page+1}"))
    rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)

def get_acc_kb(no):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 START SMART FARM", callback_data=f"run_{no}")],
        [InlineKeyboardButton(text="🔧 UPDATE IDS", callback_data=f"edit_{no}")],
        [InlineKeyboardButton(text="🛑 STOP", callback_data=f"stop_{no}"), InlineKeyboardButton(text="🔙 BACK", callback_data="page_1")]
    ])

# -------------------- HANDLERS -------------------- #

@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    if str(m.chat.id) != MY_CHAT_ID: return
    await m.answer("🛰 <b>Laser Cash 30-Slot Manager Active</b>", reply_markup=get_main_menu(), parse_mode="HTML")

@dp.message(F.text == "🏦 ACCOUNT BANK")
async def open_bank(m: types.Message):
    await m.answer("Select Account slot to configure or run:", reply_markup=get_bank_kb(1))

@dp.message(F.text == "📦 EXPORT ALL TOKENS")
async def export_tokens(m: types.Message):
    formatted = "ACCOUNTS = " + json.dumps(USER_ACCOUNTS, indent=4)
    await m.answer(f"📋 <b>Full Bank Dictionary:</b>\n\n<code>{formatted}</code>", parse_mode="HTML")

@dp.callback_query(F.data.startswith("page_"))
async def cb_page(c: types.CallbackQuery):
    await c.message.edit_reply_markup(reply_markup=get_bank_kb(int(c.data.split("_")[1])))

@dp.callback_query(F.data.startswith("view_"))
async def cb_view(c: types.CallbackQuery):
    no = c.data.split("_")[1]
    acc = USER_ACCOUNTS[no]
    status = "✅ Configured" if acc['token'] else "❌ Empty"
    msg = f"📂 <b>Account Slot {no}</b>\nStatus: {status}\n\nToken: <code>{acc['token'][:15] if acc['token'] else 'None'}...</code>"
    await c.message.edit_text(msg, reply_markup=get_acc_kb(no), parse_mode="HTML")

# --- UPDATE LOGIC (Step by Step) ---

@dp.callback_query(F.data.startswith("edit_"))
async def cb_edit(c: types.CallbackQuery, state: FSMContext):
    no = c.data.split("_")[1]
    await state.update_data(editing_no=no)
    await c.message.answer(f"🛠 Updating Account {no}\nStep 1: Send <b>Bearer Token</b>:", parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    await state.set_state(SetupStates.waiting_for_bearer)

@dp.message(SetupStates.waiting_for_bearer)
async def get_bearer(m: types.Message, state: FSMContext):
    token = m.text.replace("Bearer ", "").strip()
    await state.update_data(token=token)
    await m.answer("Step 2: Send <b>Device ID</b>:")
    await state.set_state(SetupStates.waiting_for_device)

@dp.message(SetupStates.waiting_for_device)
async def get_device(m: types.Message, state: FSMContext):
    await state.update_data(device=m.text.strip())
    await m.answer("Step 3: Send <b>Subscription ID</b>:")
    await state.set_state(SetupStates.waiting_for_sub)

@dp.message(SetupStates.waiting_for_sub)
async def get_sub(m: types.Message, state: FSMContext):
    data = await state.get_data()
    no = data['editing_no']
    USER_ACCOUNTS[no] = {
        "token": data['token'],
        "device": data['device'],
        "sub": m.text.strip()
    }
    save_data(USER_ACCOUNTS)
    await m.answer(f"✅ <b>Account {no} Updated & Saved!</b>", reply_markup=get_main_menu(), parse_mode="HTML")
    await state.clear()

# --- RUN LOGIC ---

@dp.callback_query(F.data.startswith("run_"))
async def cb_run(c: types.CallbackQuery):
    no = c.data.split("_")[1]
    if not USER_ACCOUNTS[no]['token']: return await c.answer("Account not configured!")
    if active_tasks.get(no): return await c.answer("Already Running!")
    
    active_tasks[no] = asyncio.create_task(worker_loop(no))
    await c.answer("Mission Started 🚀")

async def worker_loop(no):
    tag = f"<b>[Acc {no}]</b>"
    async with httpx.AsyncClient(http2=True, verify=False, timeout=30) as client:
        try:
            await farm_gems(client, no, tag)
            await play_games(client, no, tag)
            await send_log(f"🏁 {tag} Finished.")
        except Exception as e: await send_log(f"❌ {tag} Error: {str(e)}")
        finally: active_tasks[no] = None

@dp.callback_query(F.data.startswith("stop_"))
async def cb_stop(c: types.CallbackQuery):
    no = c.data.split("_")[1]
    if active_tasks.get(no):
        active_tasks[no].cancel()
        active_tasks[no] = None
        await c.answer("Stopped.")

async def main():
    app = web.Application(); app.router.add_get("/", lambda r: web.Response(text="RUNNING"))
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', PORT).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
