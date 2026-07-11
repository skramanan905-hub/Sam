import json, httpx, time, uuid, random, asyncio, os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiohttp import web

# ==================== CONFIGURATION ====================
API_TOKEN = "8945005329:AAFqBkXDh2Yqh38GmGm84bbVTsGFBYrvGY4"
MY_CHAT_ID = "1827265590"
BASE_URL = "https://gameoopadmin.bonixgames.com/api"
PORT = int(os.getenv("PORT", 10000))

# ==================== THE 30-ACCOUNT ID BANK ====================
ACCOUNTS = {
    "1": {"device": "c50b8e111c711fa2", "sub": "1734a8f7-8579-4131-89ee-01ead3a69f59", "token": "94242|EAwjg3IjN0wjX6zASG9HP3Dki3neneAnkNm0r9F05cabab7d"},
    "2": {"device": "8c608ccb6861f205", "sub": "2e5f8fc6-b2fd-43f2-b4dc-fd86a38603cb", "token": "94144|9iqOU9PPgu4FonsBmcqDSdCB6zmAFt12gnIts2dH1023e519"},
    "3": {"device": "757f81e4a58b709e", "sub": "34a2090b-1061-4955-8646-d463bc163f1b", "token": "94150|YsNwZ4utLCiDVDkRQV4k3ZBALqL2e1qyttkPzpep7258510a"},
    "4": {"device": "a9448298ff1b06e4", "sub": "c491c0dd-fb73-4497-85a7-a3e5a25cc9fc", "token": "94154|E2aAamiRbxJNyMrZ4mCopvCVQi94PYjjTcyZo6et9c72898e"},
    "5": {"device": "935287b13c36747d", "sub": "06b5645e-99e8-41e6-9a65-8d4f96f4d163", "token": "94159|HWhQlekMq29crbG9LAgdKt1lxjmBin2kXY2EPWz0242bc1a8"},
    "6": {"device": "50b980414bfbe957", "sub": "bbc9ac72-1fb6-4c45-a406-4769e44ff9af", "token": "94161|g0WSZ1pVI6G6BjidoANJkR6r2Q8iHj5E8uJhlDRX6a235cac"},
    "7": {"device": "59c7856b881667e0", "sub": "faea1598-5512-4e2c-be6b-9af4786a30c9", "token": "179419|7u44pZFQfkmXKXXp2VVR7XFsKrTigVUHCxqxUaG6fca64d59"},
    "8": {"device": "7e8d860ed2a6fd36", "sub": "e799a527-05dc-488c-a71d-f84c01e44935", "token": "94174|Xx93xCl8yerXc62JgRkVn6IKnrTVyyGZxYiF1N0X98ad132a"},
    "9": {"device": "67ab8b281ed06bcf", "sub": "cdad2035-ab06-4d25-b305-78ebe597e953", "token": "94183|Q1B2Kb6QBe607MuwahgOosChQix1OMKvn22vTarof9b85597"},
    "10": {"device": "ed73b96f356d99eb", "sub": "05e8c064-a122-45fe-9b72-617b67b8d8de", "token": "94190|0PD49NIeq9TBj8YIFcZVuQnRL7fXLgbvJwry5N6p6e841659"},
    "11": {"device": "0148ca028ffd2032", "sub": "0c586d57-42cb-40b5-9a09-8bfcefa3b8a1", "token": "136261|6B7CHMeZurANX7ZTcIPABAWKCh1Yvk7LGHqKPoaZ50363120"},
    "12": {"device": "0b56bf2ccc189dca", "sub": "608bcd4b-18e3-4978-898c-d4b4dd0eabf3", "token": "136147|Q9G0qwejDVse0NqUhPwYbZ51TgR6mLtaas87HKhjbdbc4205"},
    "13": {"device": "c8adb8ccdbdd02a5", "sub": "ab377498-e827-45aa-b6a1-c9505d918539", "token": "136159|lJT8NfPuO6K7LBqdOUb2LxzY7a5ZPOTBVrcuwNgv4974ebbf"},
    "14": {"device": "b1bcbde518f8803d", "sub": "0248c9cd-b7bd-48c2-9f91-3907dd0784e5", "token": "136169|nkbKB6I8rIKGneKbW9AclTapRVGXSkmgBnnRUsPXf3bbf721"},
    "15": {"device": "e681be8862881774", "sub": "c9eb0969-7bd7-416f-9243-581ca628c8f1", "token": "136223|p5T0qSXhxpBkzmTXDeVRdtcXan5FaCDHeTTnXVPg1200fa1b"},
    "16": {"device": "df9fb3a2aeb2850c", "sub": "7dc338c0-5fb6-45a3-8130-c5bac584293a", "token": "94220|Pn39QJ10XtUbG91CPnApj96mX6E25KIefcrMzBq030f6de1c"},
    "17": {"device": "ad5b6a0f9f699147", "sub": "b2af71eb-6995-4d93-b152-06347f78446c", "token": "99521|2kvy8sff5fUCFkYXTOq6o0qUWIhv2jNzmXqud9KA5f54b7bc"},
    "18": {"device": "96695f29dc830fd0", "sub": "94b42644-45ce-42c7-a7cb-775b796b4cf8", "token": "94223|g4dfsRDIiNDwfhg3YDjxTFvhpXH6GsnluOv0z7Bv18c9c828"},
    "19": {"device": "bb3e60cc26139526", "sub": "775def48-492d-4c55-b386-c48f65cf5375", "token": "94230|GcJEK3IX3Oo0prgkxzlWVOnAEsAfoKdCwNcD7nKQ6a740621"},
    "20": {"device": "f4d96302da34b3b3", "sub": "875850bf-8619-4dee-aefc-736e01326266", "token": "94236|vbjbKLEOrAgA8V8aR34FEi7bDoAWYO8Fyco411v2105bfd18"},
    "21": {"device": "fde7672c165e304c", "sub": "5661816f-e278-46f7-86eb-c267040afb4a", "token": "121294|AE1x5rJEmVLXpLD2Mj3cEg1ns1ufHCuO9iFduU1f40868442"},
    "22": {"device": "12ad69cf60eeb792", "sub": "085dccbb-ed70-424a-8d88-5114037aaa67", "token": "121308|Yh6rUHCdHmbFL0Tm0QnzwptYsOumXcoU1vvzhktzebcda5f9"},
    "23": {"device": "0bcb6ee9ad19352b", "sub": "0ea5b681-d0ca-4fa8-9000-40c0fb811bd1", "token": "121322|S0wEdcjaYPzjAdIaDgcCreStIcyWIezxs55G6LWsf79a9971"},
    "24": {"device": "c8126689bcceaa05", "sub": "cdb4487b-57b9-4cd6-8a66-854b70f2679b", "token": "121334|l6S9FIikh5a9ikSut27Ze8Rg44j9Mb3cnQ5nT0km6d53fb9c"},
    "25": {"device": "c2206ba2f9f9189e", "sub": "0e0e39ef-ca67-46bc-bfa2-332ddde00d40", "token": "121344|A5RLf2zUCuNJLQY28Ds4FpZE8DzSONYEWgjtb4xxe939dd8b"},
    "26": {"device": "e6f66c464389aed4", "sub": "0918809c-8c67-4520-afb3-c784b5da4c4b", "token": "121353|DGA3fXvLncA8Ywx2oiy7YOfUdihMIR9SGSSydZPm53459f9b"},
    "27": {"device": "df04616f80a32c7d", "sub": "13e8e5e1-5d05-4eb7-ab78-b3b5a0c38ce1", "token": "121365|cAlM9tu6wI0ahnebvWSkig5VkNYi9tS1V3L4DhXj52801c9f"},
    "28": {"device": "31813ae3941c0b87", "sub": "3b51a0ce-03af-446a-88d4-48f5f0220a8f", "token": "121371|wBj9vheWi2jznntP2Nsk4tX9RLxbQAnK3Vi9Da0C20460ed0"},
    "29": {"device": "2b903f0dd147891f", "sub": "ff52e064-07b5-4b28-8653-8ed9886a5e47", "token": "121373|KUg89zNNCfGWEJmJ6YQKOpfBVwgNesgcYH16COqMd138a9be"},
    "30": {"device": "cba94956c032c718", "sub": "6aa94054-090a-42bd-b6e0-deb00c4e47d2", "token": "121383|tmzt5dRUSZ8zW20DhMUbWu9pBCuNBejukqPwihBEb368fc29"}
}

bot = Bot(token=API_TOKEN)
dp = Dispatcher()
active_tasks = {}

# -------------------- API HELPERS -------------------- #

def get_headers(no):
    acc = ACCOUNTS[no]
    return {
        "user-agent": "MyApp/1.2.3 (android)",
        "authorization": f"Bearer {acc['token']}",
        "content-type": "application/json",
        "x-request-nonce": str(uuid.uuid4()),
        "x-subscription-id": acc['sub'],
        "x-device-id": acc['device'],
        "x-request-timestamp": str(int(time.time() * 1000)),
        "x-app-version": "1.2.3",
        "x-platform": "android",
        "host": "gameoopadmin.bonixgames.com"
    }

async def send_log(msg):
    try: await bot.send_message(MY_CHAT_ID, msg, parse_mode="HTML")
    except: pass

# -------------------- EARNING MODULES (RESTORED) -------------------- #

async def farm_gems(client, no, tag):
    while True:
        r = await client.get(f"{BASE_URL}/super-offers", headers=get_headers(no))
        if "limit" in r.text.lower() or not r.json().get("data"): break
        offer = r.json()["data"]
        if offer["can_unlock"] or offer["can_earn"]:
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

# -------------------- PROFILE & HISTORY & WITHDRAW -------------------- #

async def fetch_profile(client, no):
    r = await client.get(f"{BASE_URL}/v2/get-home-data", headers=get_headers(no))
    user = r.json().get("data", {}).get("user", {})
    return user 

async def get_history_layout(client, no):
    r = await client.get(f"{BASE_URL}/withdrawal-history", headers=get_headers(no))
    history = r.json().get("data", [])
    if not history: return "❌ No history found."
    
    msg = "📜 <b>Withdrawal History</b>\n\n"
    for item in history[:3]:
        code = item.get("redeem_code", {}).get("code", "Wait...")
        pin = item.get("card_no", "N/A")
        msg += (f"━━━━━━━━━━━━━━\n"
                f"💵 {item['withdrawal_method']['title']}\n"
                f"✅ <b>YOUR CODE:</b>\n<code>{code}</code>\n"
                f"🔑 <b>Your Gift Code Pin:</b>\n<code>{pin}</code>\n"
                f"📅 {item['created_at'][:16]}\n")
    return msg

async def start_withdraw(client, no, method_id):
    user = await fetch_profile(client, no)
    payload = {
        "withdrawal_method_id": method_id,
        "payment_details": user.get("email"),
        "phone_number": user.get("phone_number")
    }
    r = await client.post(f"{BASE_URL}/withdrawal-requests", json=payload, headers=get_headers(no))
    if r.json().get("status") == "success":
        return "🎉 <b>Success!</b> Gift code generated. Check History."
    return f"❌ <b>Error:</b> {r.json().get('message')}"

# -------------------- UI & HANDLERS -------------------- #

def get_bank_kb(page=1):
    btns = []
    start = (page-1)*10 + 1
    for i in range(start, start+10):
        s = "🟢" if str(i) in active_tasks and active_tasks[str(i)] else "🔴"
        btns.append(InlineKeyboardButton(text=f"{s} Acc {i}", callback_data=f"view_{i}"))
    rows = [btns[i:i+2] for i in range(0, len(btns), 2)]
    nav = []
    if page > 1: nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"page_{page-1}"))
    if page < 3: nav.append(InlineKeyboardButton(text="➡️", callback_data=f"page_{page+1}"))
    rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)

def get_acc_kb(no):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 PROFILE", callback_data=f"prof_{no}"), InlineKeyboardButton(text="📖 HISTORY", callback_data=f"hist_{no}")],
        [InlineKeyboardButton(text="⚡ SMART ALL-IN-ONE", callback_data=f"smart_{no}")],
        [InlineKeyboardButton(text="💎 GEMS", callback_data=f"gems_{no}"), InlineKeyboardButton(text="🎮 GAMES", callback_data=f"play_{no}")],
        [InlineKeyboardButton(text="📺 ADS", callback_data=f"ads_{no}"), InlineKeyboardButton(text="📖 READ", callback_data=f"read_{no}")],
        [InlineKeyboardButton(text="💳 REDEEM ₹10", callback_data=f"draw_7_{no}"), InlineKeyboardButton(text="💳 REDEEM ₹20", callback_data=f"draw_8_{no}")],
        [InlineKeyboardButton(text="🛑 STOP", callback_data=f"stop_{no}"), InlineKeyboardButton(text="🔙 BACK", callback_data="page_1")]
    ])

@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    if str(m.chat.id) != MY_CHAT_ID: return
    await m.answer("🏦 <b>Manager Active (v1.2.3)</b>", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🏦 ACCOUNT BANK")]], resize_keyboard=True))

@dp.message(F.text == "🏦 ACCOUNT BANK")
async def open_bank(m: types.Message):
    await m.answer("Select Account:", reply_markup=get_bank_kb(1))

@dp.callback_query()
async def cb_handler(c: types.CallbackQuery):
    d = c.data.split("_")
    action, no = d[0], d[-1]
    
    async with httpx.AsyncClient(http2=True, verify=False) as client:
        if action == "page": await c.message.edit_reply_markup(reply_markup=get_bank_kb(int(no)))
        elif action == "view":
            user = await fetch_profile(client, no)
            msg = f"📂 <b>Account {no}</b>\n👤 Name: {user['name']}\n💰 Coins: <b>{user['coins']}</b>"
            await c.message.edit_text(msg, reply_markup=get_acc_kb(no), parse_mode="HTML")
        elif action == "prof":
            u = await fetch_profile(client, no)
            await c.message.answer(f"👤 <b>{u['name']}</b>\n📧 {u['email']}\n💰 Coins: {u['coins']}", parse_mode="HTML")
        elif action == "hist":
            res = await get_history_layout(client, no)
            await c.message.answer(res, parse_mode="HTML")
        elif action == "draw":
            mid = d[1]
            res = await start_withdraw(client, no, mid)
            await c.message.answer(res, parse_mode="HTML")
        elif action in ["smart", "gems", "play", "ads", "read"]:
            if active_tasks.get(no): return await c.answer("Already Running!")
            active_tasks[no] = asyncio.create_task(worker_loop(no, action))
            await c.answer("Started 🚀")
        elif action == "stop":
            if active_tasks.get(no): active_tasks[no].cancel(); active_tasks[no] = None
            await c.answer("Stopped.")

# -------------------- MASTER WORKER LOOP -------------------- #

async def worker_loop(no, mode):
    tag = f"<b>[Acc {no}]</b>"
    async with httpx.AsyncClient(http2=True, verify=False, timeout=30) as client:
        try:
            if mode in ["smart", "gems"]: await farm_gems(client, no, tag)
            if mode in ["smart", "play"]: await play_games(client, no, tag)
            if mode in ["smart", "ads"]:  await watch_ads(client, no, tag)
            if mode in ["smart", "read"]: await do_reads(client, no, tag)
            await send_log(f"🏁 {tag} Finished.")
        except Exception as e: await send_log(f"❌ {tag} Error: {str(e)}")
        finally: active_tasks[no] = None

async def main():
    app = web.Application(); app.router.add_get("/", lambda r: web.Response(text="RUNNING 1.2.3"))
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', PORT).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
