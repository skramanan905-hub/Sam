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

# State Management for manual entry
class AccountSetup(StatesGroup):
    waiting_for_data = State()

# In-memory storage for this session
USER_ACCOUNTS = {} # { "1": {"token": "...", "device": "...", "sub": "..."} }
active_tasks = {} 
code_database = {} 

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# -------------------- API HELPERS -------------------- #

def get_headers(acc_data):
    return {
        "user-agent": "MyApp/1.0.7 (android)",
        "accept-encoding": "gzip",
        "authorization": f"Bearer {acc_data['token']}",
        "content-type": "application/json",
        "x-request-nonce": str(uuid.uuid4()),
        "x-subscription-id": acc_data['sub'],
        "accept": "application/json",
        "x-device-id": acc_data['device'],
        "x-request-timestamp": str(int(time.time() * 1000)),
        "x-app-version": "1.0.7",
        "x-platform": "android",
        "host": "lasercashadmin.bonixgames.com"
    }

async def send_log(msg):
    try: await bot.send_message(MY_CHAT_ID, msg, parse_mode="HTML")
    except: pass

# -------------------- EARNING MODULES -------------------- #

async def farm_gems(client, acc, tag):
    while True:
        r = await client.get(f"{BASE_URL}/super-offers", headers=get_headers(acc))
        if "limit" in r.text.lower() or not r.json().get("data"): break
        offer = r.json()["data"]
        oid = offer["id"]
        
        if offer.get("can_unlock") or offer.get("can_earn"):
            if offer.get("can_unlock"):
                await client.post(f"{BASE_URL}/super-offers/unlock", json={"super_offer_id": oid, "timing": "0"}, headers=get_headers(acc))
            await asyncio.sleep(2)
            if offer.get("can_earn") or True:
                await client.post(f"{BASE_URL}/super-offers/earn", json={"super_offer_id": oid}, headers=get_headers(acc))
                await send_log(f"💰 {tag}: Super Offer {oid} Claimed!")
        else:
            h = get_headers(acc)
            # Admob Heartbeat logic for Laser Cash Gems
            await asyncio.gather(
                client.post(f"{BASE_URL}/v2/ad-impression", json={"provider":"admob","ad_type":"rewarded"}, headers=h),
                client.post(f"{BASE_URL}/adx/update", json={"adx_item_id":0}, headers=h)
            )
            await asyncio.sleep(random.randint(3, 5))
            claim = await client.post(f"{BASE_URL}/play-games/play", json={"timing": "115000", "is_ad_seen": True}, headers=h)
            if "limit" in claim.text.lower(): break
        await asyncio.sleep(2)

async def play_games(client, acc, tag):
    r = await client.get(f"{BASE_URL}/games", headers=get_headers(acc))
    for g in r.json().get("data", []):
        if not g.get("claimed"):
            await asyncio.sleep(8)
            await client.post(f"{BASE_URL}/games/{g['id']}/play", json={"timing": "97000", "is_ad_seen": True}, headers=get_headers(acc))

async def watch_ads(client, acc, tag):
    r = await client.get(f"{BASE_URL}/watch-ads", headers=get_headers(acc))
    for ad in r.json().get("data", []):
        if ad.get("can_watch"):
            h = get_headers(acc)
            await client.post(f"{BASE_URL}/v2/ad-impression", json={"provider":"admob","ad_type":"rewarded"}, headers=h)
            await asyncio.sleep(5)
            await client.post(f"{BASE_URL}/watch-ads/watch", json={"watch_ad_id": ad['id'], "timing": "36000", "is_ad_seen": True}, headers=h)

async def do_reads(client, acc, tag):
    while True:
        st = await client.get(f"{BASE_URL}/read-earn/user-status", headers=get_headers(acc))
        if not st.json().get("can_complete_more"): break
        r_t = await client.get(f"{BASE_URL}/read-earn/random-task", headers=get_headers(acc))
        if r_t.json().get("status") == "success":
            task = r_t.json()["data"]
            await asyncio.sleep(125)
            p = {"task_id": task["id"], "verify_code": task["verify_code"], "timing": "130000", "is_ad_seen": True}
            await client.post(f"{BASE_URL}/read-earn/complete-task", json=p, headers=get_headers(acc))
        else: break

# -------------------- UI & HANDLERS -------------------- #

def get_main_menu():
    kb = [[KeyboardButton(text="➕ ADD ACCOUNT")], [KeyboardButton(text="🏦 ACCOUNT BANK")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_bank_kb():
    btns = []
    for acc_id in USER_ACCOUNTS.keys():
        s = "🟢" if acc_id in active_tasks and active_tasks[acc_id] else "🔴"
        btns.append(InlineKeyboardButton(text=f"{s} Laser {acc_id}", callback_data=f"view_{acc_id}"))
    rows = [btns[i:i+2] for i in range(0, len(btns), 2)]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def get_acc_kb(no):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ SMART FARM", callback_data=f"smart_{no}")],
        [InlineKeyboardButton(text="🛑 STOP", callback_data=f"stop_{no}"), InlineKeyboardButton(text="🔙 BACK", callback_data="back_bank")]
    ])

@dp.message(Command("start"))
async def start(m: types.Message):
    if str(m.chat.id) != MY_CHAT_ID: return
    await m.answer("🛰 <b>Laser Cash Bot v1.0.7 Active</b>", reply_markup=get_main_menu(), parse_mode="HTML")

@dp.message(F.text == "➕ ADD ACCOUNT")
async def add_acc_req(m: types.Message, state: FSMContext):
    await m.answer("Send data in format:\n<code>Bearer|DeviceID|SubID</code>", parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    await state.set_state(AccountSetup.waiting_for_data)

@dp.message(AccountSetup.waiting_for_data)
async def save_acc(m: types.Message, state: FSMContext):
    try:
        parts = m.text.split("|")
        token = parts[0].replace("Bearer ", "").strip()
        device = parts[1].strip()
        sub = parts[2].strip()
        
        acc_id = str(len(USER_ACCOUNTS) + 1)
        USER_ACCOUNTS[acc_id] = {"token": token, "device": device, "sub": sub}
        
        await m.answer(f"✅ Account {acc_id} saved to Bank!", reply_markup=get_main_menu())
    except:
        await m.answer("❌ Format Error! Use: Bearer|Device|Sub")
    await state.clear()

@dp.message(F.text == "🏦 ACCOUNT BANK")
async def open_bank(m: types.Message):
    if not USER_ACCOUNTS: return await m.answer("Bank is empty. Add an account first.")
    await m.answer("Select Account:", reply_markup=get_bank_kb())

@dp.callback_query()
async def cb_handler(c: types.CallbackQuery):
    d = c.data.split("_")
    if d[0] == "back": await c.message.edit_text("Select Account:", reply_markup=get_bank_kb())
    elif d[0] == "view":
        acc_id = d[1]
        msg = f"📂 <b>Laser Account {acc_id}</b>\n📱 Device: <code>{USER_ACCOUNTS[acc_id]['device'][:8]}...</code>"
        await c.message.edit_text(msg, reply_markup=get_acc_kb(acc_id), parse_mode="HTML")
    elif d[0] == "smart":
        acc_id = d[1]
        if active_tasks.get(acc_id): return await c.answer("Already Running!")
        active_tasks[acc_id] = asyncio.create_task(worker_loop(acc_id))
        await c.answer("Farming Started 🚀")
    elif d[0] == "stop":
        acc_id = d[1]
        if active_tasks.get(acc_id): active_tasks[acc_id].cancel(); active_tasks[acc_id] = None
        await c.answer("Stopped.")

# -------------------- MASTER LOOP -------------------- #

async def worker_loop(acc_id):
    tag = f"<b>[Laser {acc_id}]</b>"
    acc_data = USER_ACCOUNTS[acc_id]
    async with httpx.AsyncClient(http2=True, verify=False, timeout=30) as client:
        try:
            await farm_gems(client, acc_data, tag)
            await play_games(client, acc_data, tag)
            await watch_ads(client, acc_data, tag)
            await do_reads(client, acc_data, tag)
            await send_log(f"🏁 {tag} <b>Cycle Finished.</b>")
        except Exception as e: await send_log(f"❌ {tag} Error: {str(e)}")
        finally: active_tasks[acc_id] = None

async def main():
    app = web.Application(); app.router.add_get("/", lambda r: web.Response(text="RUNNING 1.0.7"))
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', PORT).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
