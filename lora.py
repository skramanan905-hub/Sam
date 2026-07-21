import json, httpx, time, uuid, random, asyncio, os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiohttp import web

# ==================== CONFIGURATION ====================
API_TOKEN = "8616821892:AAGvSzp-5SRGyQO4V-wcTX-YPt4j8XrZcVg"
MY_CHAT_ID = "1827265590"
BASE_URL = "https://flipcontrol.flipdiamond.com/api"
PORT = int(os.getenv("PORT", 10000))

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# SESSION STORAGE
state = {
    "token": None,
    "device_id": None,
    "sub_id": "",
    "step": "idle", # wait_token, wait_device, wait_sub, ready
    "task": None
}
code_waiter = None # To catch the Read code

# Keyboard
def get_main_kb():
    kb = [[KeyboardButton(text="🚀 START FARMING")], [KeyboardButton(text="🛑 STOP BOT")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# -------------------- API HELPERS -------------------- #

def get_headers():
    return {
        "user-agent": "MyApp/12.5.7 (android)",
        "accept-encoding": "gzip",
        "authorization": f"Bearer {state['token']}",
        "content-type": "application/json",
        "x-request-nonce": str(uuid.uuid4()),
        "x-subscription-id": state['sub_id'],
        "accept": "application/json",
        "x-device-id": state['device_id'],
        "x-request-timestamp": str(int(time.time() * 1000)),
        "x-app-version": "12.5.7",
        "x-platform": "android",
        "host": "flipcontrol.flipdiamond.com"
    }

async def send_log(msg):
    try: await bot.send_message(MY_CHAT_ID, msg, parse_mode="HTML")
    except: pass

# -------------------- FARMING LOGIC -------------------- #

async def worker_loop():
    async with httpx.AsyncClient(http2=True, verify=False, timeout=30) as client:
        await send_log("🤖 <b>Bot Active.</b> Starting sequence...")
        try:
            # 1. GEMS & SUPERS (3-5s)
            while True:
                r = await client.get(f"{BASE_URL}/super-offers", headers=get_headers())
                res = r.json()
                if "limit" in r.text.lower() or not res.get("data"): break
                offer = res["data"]
                if offer["can_unlock"] or offer["can_earn"]:
                    await client.post(f"{BASE_URL}/super-offers/unlock", json={"super_offer_id": offer["id"], "timing": "0"}, headers=get_headers())
                    await asyncio.sleep(2); await client.post(f"{BASE_URL}/super-offers/earn", json={"super_offer_id": offer["id"]}, headers=get_headers())
                    await send_log("💰 Super Offer Claimed!")
                else:
                    h = get_headers()
                    await asyncio.gather(client.post(f"{BASE_URL}/v2/ad-impression", json={"provider":"digital_turbine","ad_type":"rewarded"}, headers=h),
                                       client.post(f"{BASE_URL}/track/dt-ads", json={"dt_item_id":0}, headers=h))
                    await asyncio.sleep(random.randint(3, 5))
                    claim = await client.post(f"{BASE_URL}/play-games/play", json={"timing": "45200", "is_ad_seen": True}, headers=h)
                    if "limit" in claim.text.lower(): break
                await asyncio.sleep(1)

            # 2. EXTRA GAMES (2x Bonus)
            r_g = await client.get(f"{BASE_URL}/games", headers=get_headers())
            for g in r_g.json().get("data", []):
                if not g.get("claimed"):
                    h = get_headers()
                    await client.post(f"{BASE_URL}/v2/ad-impression", json={"provider":"digital_turbine","ad_type":"rewarded"}, headers=h)
                    await client.post(f"{BASE_URL}/track/dt-ads", json={"dt_item_id":0}, headers=h)
                    await asyncio.sleep(10)
                    await client.post(f"{BASE_URL}/games/{g['id']}/play", json={"timing": "182198", "is_ad_seen": True}, headers=h)
            
            # 3. WATCH ADS
            r_a = await client.get(f"{BASE_URL}/watch-ads", headers=get_headers())
            for ad in r_a.json().get("data", []):
                if ad.get("can_watch"):
                    h = get_headers()
                    await client.post(f"{BASE_URL}/v2/ad-impression", json={"provider":"digital_turbine","ad_type":"rewarded"}, headers=h)
                    await asyncio.sleep(6); await client.post(f"{BASE_URL}/watch-ads/watch", json={"watch_ad_id": ad['id'], "timing": "35000", "is_ad_seen": True}, headers=h)

            # 4. INTERACTIVE READ
            while True:
                r_st = await client.get(f"{BASE_URL}/read-earn/user-status", headers=get_headers())
                if not r_st.json().get("can_complete_more"): break
                r_t = await client.get(f"{BASE_URL}/read-earn/random-task", headers=get_headers())
                t_json = r_t.json()
                if t_json.get("status") == "success":
                    task = t_json["data"]
                    await send_log(f"📖 <b>READ TASK</b>\nLink: {task['website_url']}\n\n<i>Waiting 125s... Find the code!</i>")
                    await asyncio.sleep(125)
                    
                    global code_waiter
                    code_waiter = asyncio.get_running_loop().create_future()
                    await send_log(f"🔔 <b>TIMER OVER!</b>\nSend code for Task {task['id']}:")
                    
                    user_code = await code_waiter
                    await client.post(f"{BASE_URL}/read-earn/complete-task", json={"task_id": task["id"], "verify_code": user_code, "timing": "224584", "is_ad_seen": True}, headers=get_headers())
                    await send_log("✅ Read Success!")
                else: break

            await send_log("🏁 <b>FINISHED!</b> Account fully cleared.")
        except Exception as e: await send_log(f"❌ Error: {e}")
        finally: state['task'] = None

# -------------------- TG HANDLERS -------------------- #

@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    if str(m.chat.id) != MY_CHAT_ID: return
    state["step"] = "wait_token"
    await m.answer("🔧 <b>Step [1/3]</b>: Paste <b>Bearer Token</b>:", parse_mode="HTML", reply_markup=ReplyKeyboardRemove())

@dp.message()
async def input_handler(m: types.Message):
    if str(m.chat.id) != MY_CHAT_ID: return
    
    # READ CODE CATCHER
    global code_waiter
    if code_waiter and not code_waiter.done():
        code_waiter.set_result(m.text.strip())
        return

    # SETUP FLOW
    if state["step"] == "wait_token":
        state["token"] = m.text.replace("Bearer ", "").strip()
        state["step"] = "wait_device"; await m.answer("🔧 <b>Step [2/3]</b>: Paste <b>Device ID</b>:", parse_mode="HTML")
    elif state["step"] == "wait_device":
        state["device_id"] = m.text.strip()
        state["step"] = "wait_sub"; await m.answer("🔧 <b>Step [3/3]</b>: Paste <b>Subscription ID</b> (or .):", parse_mode="HTML")
    elif state["step"] == "wait_sub":
        state["sub_id"] = "" if m.text.strip() == "." else m.text.strip()
        state["step"] = "ready"
        await m.answer("✅ <b>IDs Saved!</b>", reply_markup=get_main_kb())

    # BUTTONS
    elif m.text == "🚀 START FARMING":
        if state["step"] != "ready": return await m.answer("Run /start first!")
        if state["task"]: state["task"].cancel()
        state["task"] = asyncio.create_task(worker_loop())
    elif m.text == "🛑 STOP BOT":
        if state["task"]: state["task"].cancel(); state["task"] = None
        await m.answer("Stopped.")

async def main():
    app = web.Application(); app.router.add_get("/", lambda r: web.Response(text="OK"))
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', PORT).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
