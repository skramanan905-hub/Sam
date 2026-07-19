import json, httpx, time, uuid, random, asyncio, os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiohttp import web

# ==================== CONFIGURATION ====================
API_TOKEN = "8864480840:AAE2obzpWIhDPVR4NjhXvNgRYPF9X08Nfi4"
MY_CHAT_ID = "1827265590"
BASE_URL = "https://flipcontrol.flipdiamond.com/api"
PORT = int(os.getenv("PORT", 10000))

# ==================== THE 30-ACCOUNT BANK ====================
ACCOUNTS = {
    "1": {"token": "483270|WZpYVa83I7wDMaiFPxhM91nCCj6Sc9pAyzMZkKqO1d8cfce9", "device": "c50b8e111c711fa2", "sub": "df3defbf-db22-4eb5-94cc-c8a7d5904a6b"},
    "2": {"token": "483288|tqaknRpAhcqjDEwq9I4SMTIGYJ45OaQq7c4UVD2v6290ae26", "device": "8c608ccb6861f205", "sub": "dd5d4022-ad51-4b62-bf45-1fcf3d8c51e8"},
    "3": {"token": "483300|fpkicD2QvZQOfH3gVqhCpQUACfgzb70cCGWeEKRR235f6b6d", "device": "757f81e4a58b709e", "sub": "98d3870e-72ed-4fed-b555-653db6666578"},
    "4": {"token": "483370|2i8bNu6wvQs2FBW4O7kGC6cnGwTcqAb8X2AtV8D9ad433956", "device": "a9448298ff1b06e4", "sub": "1303a501-a2e1-4b59-ac65-08b14d2c9ff6"},
    "5": {"token": "483377|FDb7HmEb7arfgWHSrGbDLULSycjUcWyvggDkV4iy1d21e6c7", "device": "935287b13c36747d", "sub": "bb79a984-2bd1-4a47-9056-253214d5873e"},
    "6": {"token": "483382|fQW9NcoVVVKGRj2Vpd7rV0XUVFArw3OcHe0PeLj6bc423b44", "device": "50b980414bfbe957", "sub": "cfe36b3a-98bd-4b1a-b5bd-1f14cecb89a0"},
    "7": {"token": "483389|MCvjBFdOjTHXbHqlMI6NwqGsqRlN2UeNR1snyGU6ce0704f0", "device": "59c7856b881667e0", "sub": "a3303478-2f25-4b9c-9b6d-86da9c604363"},
    "8": {"token": "483400|EOD5cntgE0jbYeUwjNQsEijw5Czeu08sQ41eNATA9dbe47f0", "device": "7e8d860ed2a6fd36", "sub": "252db7fb-b07b-400f-9216-70c4d6703460"},
    "9": {"token": "483408|osDxE76inSRNnpGLU4hQMieIulQVjGMKwG8LbEtc796db9d3", "device": "67ab8b281ed06bcf", "sub": "9252d6f5-1605-4f8b-ba5b-5beb1ff24f2a"},
    "10": {"token": "483420|SGPKtylUqx7RJHcdIwqHFD4SSz4bgFtofIpp9rMI330ec655", "device": "ed73b96f356d99eb", "sub": "91c1d550-bda0-4c9b-9921-f3ca0095c0c1"},
    "11": {"token": "483424|GdFqCRHibgLQPW2Go3L1T8EMfP7wbUkeshxmqPQme9d610bc", "device": "0148ca028ffd2032", "sub": "a4ef1398-cce6-480e-b31e-750a42daef16"},
    "12": {"token": "483436|dDNpsPq3eMB705lzp0kwZoKvzfVsbG4j39eWrQDv267aa944", "device": "0b56bf2ccc189dca", "sub": "f4ab614b-d606-4d1e-8301-75455f0ebfbf"},
    "13": {"token": "483449|A8FdKCA0K5M2gnpOvQukvO9O4tDLHoSh0ljLykm97586a168", "device": "c8adb8ccdbdd02a5", "sub": "ac069173-68c9-42c4-bcac-64a93dd02eca"},
    "14": {"token": "483455|4VZAXzkjyQ3VuUs66nbhjukSqkMz1eFrqHxN27cxcc120ed3", "device": "b1bcbde518f8803d", "sub": "8e6de487-5dc8-4390-a071-88655ef30c22"},
    "15": {"token": "483458|MUMrS5PRRPRiftTWWnuxUGrY2ER2VVRnEI0dieWe6ecdf24f", "device": "e681be8862881774", "sub": "b635f5d0-b798-4da9-b1b7-f1183b92efeb"},
    "16": {"token": "483468|OoERQYYrBs5E4EufcnOygqeoCvGNWYuEtJH0N1zu7f439123", "device": "df9fb3a2aeb2850c", "sub": "d0885961-951a-4d20-a269-dbe7cf0da6a9"},
    "17": {"token": "483475|h8azQURuYI9FSJlEthtIl6aFimGG8NKLTtVQdwM7a8a39b15", "device": "ad5b6a0f9f699147", "sub": "24144988-2450-48b6-b233-7b0f22a98831"},
    "18": {"token": "483479|WQZvmLGpEAPuo7eqyZ2uSvR8QbIexb1bayt101Wg9e9e5656", "device": "96695f29dc830fd0", "sub": "8bb6f3ec-2f9d-41b8-b066-af0356292f8e"},
    "19": {"token": "483481|cNF5NXfNCPqM5lZzBeF4I7XM1FhmwXBOQ0UeM4p8b1b9a352", "device": "bb3e60cc26139526", "sub": "f33ba113-ad79-42a2-b8b0-634159e3c185"},
    "20": {"token": "483362|KrH6If90TEBEgpNknLfbjzileoCEjkdr2WGyfscQ2c22d9a6", "device": "f4d96302da34b3b3", "sub": "17f3f2cb-53b0-4caa-bb7e-460e94043ab5"},
    "21": {"token": "483341|KayEK9DyXMU5o4LApissqJlCIAOw8YKFIcReS4JO68411ec0", "device": "fde7672c165e304c", "sub": "862ff1f9-e370-4e82-826a-40843d335d5b"},
    "22": {"token": "483338|AHwP9QtaY9U7ZPGgjFJrXbWEUBdlIDnFE2Ho7ll50d65dab5", "device": "12ad69cf60eeb792", "sub": "865225e9-0178-4864-90b9-5a5517cc2992"},
    "23": {"token": "483329|9wstz5q0qY1cKrjsyvlHl9drxEbkNj2SfXvui1xL257af4f6", "device": "0bcb6ee9ad19352b", "sub": "1dc0b05b-aa01-4aa9-b899-9f413ba6d0ce"},
    "24": {"token": "483322|yfpMPqDMcv5KzXFe7r0F6TuYhsEd6UXEXWOnyvDa2c797d65", "device": "c8126689bcceaa05", "sub": "2512cf99-1647-4563-996f-3a3aa9b47b48"},
    "25": {"token": "483318|mzdErlRv0DPMGKxhhoWiWpEFMSzSdmCWCttYNYCO4d2945fa", "device": "c2206ba2f9f9189e", "sub": "6fc5643b-1eb2-493d-9085-0888c6931579"},
    "26": {"token": "483316|hNfpGujFRzmuvllqCz7tUCGX69qDTH74Xyc8oidtc46068b8", "device": "e6f66c464389aed4", "sub": "a68ac7d1-f789-4ae9-9300-4409ea8fc6e3"},
    "27": {"token": "483314|TDfA6yIeUr75bux2TRoSnkrxOSjvrMU5IzU9KYL3b8dc6cfe", "device": "df04616f80a32c7d", "sub": "11697fa4-ed68-4628-aaed-837f3122d8d2"},
    "28": {"token": "602313|rCG2fpWRUmMUUqTWF7HEbnUrDn3H8ZVbnUl9Funv91b9f2b3", "device": "31813ae3941c0b87", "sub": "01e8ae80-b873-4da0-92f5-77cf7a8ed9d3"},
    "29": {"token": "602303|VlJATqMzS3IIopVXfwgiw8LG8aHID1T1Eh8NCXu8b6583728", "device": "2b903f0dd147891f", "sub": "27d2a7e0-55d2-4840-a0f8-5b6bbbcc839e"},
    "30": {"token": "483303|GJXuoOfvWo1fp1BPutB0wTlTLuudld7vHYCOVXbk6c436c0b", "device": "cba94956c032c718", "sub": "ce063f08-d217-4f89-a028-0f05cec42df4"},
}

bot = Bot(token=API_TOKEN)
dp = Dispatcher()
active_workers = {} 
code_database = {} 
setup_lock = {} 

# -------------------- API HELPERS -------------------- #

def get_headers(no):
    acc = ACCOUNTS[no]
    return {
        "user-agent": "MyApp/12.5.7 (android)",
        "accept-encoding": "gzip",
        "authorization": f"Bearer {acc['token']}",
        "content-type": "application/json",
        "x-request-nonce": str(uuid.uuid4()),
        "x-subscription-id": acc['sub'],
        "accept": "application/json",
        "x-device-id": acc['device'],
        "x-request-timestamp": str(int(time.time() * 1000)),
        "x-app-version": "12.5.7",
        "x-platform": "android",
        "host": "flipcontrol.flipdiamond.com"
    }

async def send_log(msg):
    try: await bot.send_message(MY_CHAT_ID, msg, parse_mode="HTML")
    except: pass

# -------------------- EARNING MODULES -------------------- #

async def farm_gems_and_supers(client, no, tag):
    """Loops until all 5 Super Offers are done. Fixed v12.5.7 Status check."""
    while True:
        r = await client.get(f"{BASE_URL}/super-offers", headers=get_headers(no))
        res_json = r.json()
        
        # FIX: Check strictly for status error, ignore 'limit' in text
        if res_json.get("status") == "error" or not res_json.get("data"):
            await send_log(f"🏁 {tag}: Super Offers limit reached (Server confirmed).")
            break
            
        offer = res_json["data"]
        offer_id = offer["id"]
        
        if offer.get("can_earn"):
            await client.post(f"{BASE_URL}/super-offers/earn", json={"super_offer_id": offer_id}, headers=get_headers(no))
            await send_log(f"💰 {tag}: <b>SUPER OFFER {offer_id} CLAIMED!</b>")
            continue 
            
        if offer.get("can_unlock"):
            await client.post(f"{BASE_URL}/super-offers/unlock", json={"super_offer_id": offer_id, "timing": "0"}, headers=get_headers(no))
            continue

        # Farm Stars (Gems) - Fixed Admob Heartbeat
        h = get_headers(no)
        await asyncio.gather(
            client.post(f"{BASE_URL}/v2/ad-impression", json={"provider":"admob","ad_type":"rewarded"}, headers=h),
            client.post(f"{BASE_URL}/adx/update", json={"adx_item_id":0}, headers=h)
        )
        await asyncio.sleep(random.randint(3, 5))
        claim = await client.post(f"{BASE_URL}/play-games/play", json={"timing": "45000", "is_ad_seen": True}, headers=h)
        if "limit" in claim.text.lower(): break
        await asyncio.sleep(1)

async def farm_games(client, no, tag):
    """Farms Games 30-39 using DT Heartbeat"""
    r = await client.get(f"{BASE_URL}/games", headers=get_headers(no))
    for g in r.json().get("data", []):
        if not g.get("claimed"):
            h = get_headers(no)
            await asyncio.gather(
                client.post(f"{BASE_URL}/v2/ad-impression", json={"provider":"digital_turbine","ad_type":"rewarded"}, headers=h),
                client.post(f"{BASE_URL}/track/dt-ads", json={"dt_item_id":0}, headers=h)
            )
            await asyncio.sleep(8)
            await client.post(f"{BASE_URL}/games/{g['id']}/play", json={"timing": "182198", "is_ad_seen": True}, headers=h)
    await send_log(f"🕹 {tag}: Games cycle finished.")

async def farm_ads(client, no, tag):
    r = await client.get(f"{BASE_URL}/watch-ads", headers=get_headers(no))
    for ad in r.json().get("data", []):
        if ad.get("can_watch"):
            h = get_headers(no)
            await client.post(f"{BASE_URL}/v2/ad-impression", json={"provider":"digital_turbine","ad_type":"rewarded"}, headers=h)
            await asyncio.sleep(6)
            await client.post(f"{BASE_URL}/watch-ads/watch", json={"watch_ad_id": ad['id'], "timing": "35000", "is_ad_seen": True}, headers=h)
    await send_log(f"📺 {tag}: Ads cycle finished.")

async def farm_reads(client, no, tag):
    count = 0
    while True:
        st = await client.get(f"{BASE_URL}/read-earn/user-status", headers=get_headers(no))
        if not st.json().get("can_complete_more"): break
        r_t = await client.get(f"{BASE_URL}/read-earn/random-task", headers=get_headers(no))
        task = r_t.json().get("data")
        if task and str(task["id"]) in code_database:
            await asyncio.sleep(125)
            p = {"task_id": task["id"], "verify_code": code_database[str(task["id"])], "timing": "130000", "is_ad_seen": True}
            await client.post(f"{BASE_URL}/read-earn/complete-task", json=p, headers=get_headers(no))
            count += 1
        else: break
    if count > 0: await send_log(f"📖 {tag}: Finished {count} Reads.")

# -------------------- PROFILE & PAYOUT -------------------- #

async def fetch_user(client, no):
    r = await client.get(f"{BASE_URL}/v2/get-home-data", headers=get_headers(no))
    return r.json().get("data", {}).get("user", {})

async def handle_history(client, no):
    r = await client.get(f"{BASE_URL}/withdrawal-history", headers=get_headers(no))
    items = r.json().get("data", [])
    if not items: return "❌ No History."
    msg = "🎁 <b>FlipDiamond History</b>\n\n"
    for x in items[:3]:
        code = x.get("redeem_code", {}).get("code", "Wait...")
        pin = x.get("card_no", "N/A")
        msg += f"💵 {x['withdrawal_method']['title']}\n✅ <code>{code}</code>\n📌 <code>{pin}</code>\n\n"
    return msg

async def handle_payout(client, no, mid):
    u = await fetch_user(client, no)
    payload = {"withdrawal_method_id": mid, "payment_details": u['email'], "phone_number": u['phone_number']}
    r = await client.post(f"{BASE_URL}/withdrawal-requests", json=payload, headers=get_headers(no))
    if r.json().get("status") == "success":
        return "✅ <b>Withdrawal Success!</b>"
    return f"❌ <b>Error:</b> {r.json().get('message')}"

# -------------------- UI SETUP -------------------- #

def get_bank_kb(page=1):
    btns = []
    start = (page-1)*10 + 1
    for i in range(start, min(start+10, 31)):
        s = "🟢" if str(i) in active_workers and active_workers[str(i)] else "🔴"
        btns.append(InlineKeyboardButton(text=f"{s} Acc {i}", callback_data=f"view_{i}"))
    rows = [btns[i:i+2] for i in range(0, len(btns), 2)]
    nav = [InlineKeyboardButton(text="⬅️", callback_data=f"page_{max(1, page-1)}"), InlineKeyboardButton(text="➡️", callback_data=f"page_{min(3, page+1)}")]
    rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)

def get_acc_kb(no):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 PROFILE", callback_data=f"prof_{no}"), InlineKeyboardButton(text="📖 HISTORY", callback_data=f"hist_{no}")],
        [InlineKeyboardButton(text="⚡ SMART FARM", callback_data=f"smart_{no}")],
        [InlineKeyboardButton(text="💎 GEMS", callback_data=f"gems_{no}"), InlineKeyboardButton(text="🕹 GAMES", callback_data=f"play_{no}")],
        [InlineKeyboardButton(text="💳 ₹10", callback_data=f"wd_42_{no}"), InlineKeyboardButton(text="💳 ₹30", callback_data=f"wd_41_{no}")],
        [InlineKeyboardButton(text="💳 ₹50", callback_data=f"wd_45_{no}"), InlineKeyboardButton(text="💳 ₹100", callback_data=f"wd_43_{no}")],
        [InlineKeyboardButton(text="🛑 STOP", callback_data=f"stop_{no}"), InlineKeyboardButton(text="🔙 BACK", callback_data="page_1")]
    ])

# -------------------- MASTER HANDLERS -------------------- #

@dp.callback_query()
async def cb_handler(c: types.CallbackQuery):
    d = c.data.split("_")
    action, no = d[0], d[-1]
    async with httpx.AsyncClient(http2=True, verify=False) as client:
        if action == "page": await c.message.edit_reply_markup(reply_markup=get_bank_kb(int(no)))
        elif action == "view":
            u = await fetch_user(client, no)
            await c.message.edit_text(f"📂 <b>Acc {no}</b>\n👤 {u['name']}\n💰 {u['coins']}", reply_markup=get_acc_kb(no), parse_mode="HTML")
        elif action == "prof":
            u = await fetch_user(client, no)
            await c.message.answer(f"👤 <b>{u['name']}</b>\n📧 {u['email']}\n💰 {u['coins']}")
        elif action == "hist": await c.message.answer(await handle_history(client, no), parse_mode="HTML")
        elif action == "wd": await c.message.answer(await handle_payout(client, no, d[1]))
        elif action in ["smart", "gems", "play"]:
            if active_workers.get(no): return await c.answer("Running!")
            active_workers[no] = asyncio.create_task(master_worker(no, action))
            await c.answer("Started!")
        elif action == "stop":
            if active_workers.get(no): active_workers[no].cancel(); active_workers[no] = None
            await c.answer("Stopped.")
    await c.answer()

async def master_worker(no, mode):
    tag = f"<b>[Acc {no}]</b>"
    async with httpx.AsyncClient(http2=True, verify=False, timeout=30) as client:
        try:
            # 1. Supers & Gems (Mandatory First in All-in-One)
            if mode in ["smart", "gems"]: 
                await farm_gems_and_supers(client, no, tag)
            
            # 2. Transition (Games -> Ads -> Reads)
            if mode in ["smart", "play"]: 
                await farm_games(client, no, tag)
                await farm_ads(client, no, tag)
                await farm_reads(client, no, tag)
            
            await send_log(f"🏁 {tag} <b>Farming Complete.</b>")
        except Exception as e: await send_log(f"❌ {tag} Error: {str(e)}")
        finally: active_workers[no] = None

@dp.message(Command("start"))
async def start_cmd(m: types.Message):
    if str(m.chat.id) != MY_CHAT_ID: return
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🏦 ACCOUNT BANK")], [KeyboardButton(text="📝 UPDATE DAILY CODES")]], resize_keyboard=True)
    await m.answer("💎 <b>Flip Ultimate v12.5.7 Active</b>", reply_markup=kb, parse_mode="HTML")

@dp.message(F.text == "🏦 ACCOUNT BANK")
async def open_bank(m: types.Message):
    await m.answer("Select Account:", reply_markup=get_bank_kb(1))

@dp.message(F.text == "📝 UPDATE DAILY CODES")
async def set_codes(m: types.Message):
    setup_lock[m.chat.id] = True
    await m.answer("Send codes (ID:CODE):", reply_markup=ReplyKeyboardRemove())

@dp.message()
async def text_input(m: types.Message):
    if setup_lock.get(m.chat.id):
        for line in m.text.split("\n"):
            if ":" in line:
                tid, tcode = line.split(":")
                code_database[tid.strip()] = tcode.strip()
        del setup_lock[m.chat.id]
        await m.answer("✅ Codes Saved!")

async def main():
    app = web.Application(); app.router.add_get("/", lambda r: web.Response(text="RUNNING"))
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', PORT).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
