import json, httpx, time, asyncio, os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiohttp import web

# ==================== CONFIGURATION ====================
API_TOKEN = "8670721839:AAEgj52vhlzuDWWsVdUgviKzKh0xKCc_hqA"
MY_CHAT_ID = "1827265590"
URL = "https://us-central1-gamerush-68528.cloudfunctions.net/claimGems"
PORT = int(os.getenv("PORT", 10000))

# Store for 10 accounts
ACCOUNTS = {str(i): None for i in range(1, 11)} 
active_tasks = {} # { "1": Task }
setup_lock = {}  # { chat_id: acc_no }

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# -------------------- API LOGIC -------------------- #

def get_headers(token):
    return {
        "host": "us-central1-gamerush-68528.cloudfunctions.net",
        "authorization": f"Bearer {token}",
        "x-firebase-appcheck": "eyJlcnJvciI6IlVOS05PV05fRVJST1IifQ==",
        "content-type": "application/json; charset=utf-8",
        "user-agent": "okhttp/5.2.1"
    }

def get_payload(is_install=False):
    val = "2" if is_install else "1"
    return {
        "data": {
            "gems": {
                "@type": "type.googleapis.com/google.protobuf.Int64Value",
                "value": val
            },
            "isInstall": is_install
        }
    }

async def send_log(msg):
    try: await bot.send_message(MY_CHAT_ID, msg, parse_mode="HTML")
    except: pass

# -------------------- UI COMPONENTS -------------------- #

def get_main_menu():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🏦 ACCOUNT BANK")]], resize_keyboard=True)

def get_bank_kb():
    btns = []
    for i in range(1, 11):
        token = ACCOUNTS.get(str(i))
        status = "🟢" if str(i) in active_tasks and active_tasks[str(i)] else "🔴"
        label = f"{status} Acc {i}" if token else f"⚪ Acc {i} (Empty)"
        btns.append(InlineKeyboardButton(text=label, callback_data=f"view_{i}"))
    
    # Grid of 2 columns
    rows = [btns[i:i+2] for i in range(0, len(btns), 2)]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def get_acc_kb(no):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 START CLAIM (Option 1)", callback_data=f"claim_{no}")],
        [InlineKeyboardButton(text="🛠 INSTALL TASK (Option 2)", callback_data=f"task_{no}")],
        [InlineKeyboardButton(text="🔑 UPDATE BEARER", callback_data=f"upd_{no}")],
        [InlineKeyboardButton(text="🛑 STOP", callback_data=f"stop_{no}"), InlineKeyboardButton(text="🔙 BACK", callback_data="back_bank")]
    ])

# -------------------- WORKER LOOP -------------------- #

async def account_worker(no, token):
    tag = f"<b>[Acc {no}]</b>"
    headers = get_headers(token)
    
    async with httpx.AsyncClient(http2=True, verify=False, timeout=30) as client:
        count = 1
        try:
            while True:
                response = await client.post(URL, headers=headers, json=get_payload(False))
                
                if response.status_code == 401:
                    await send_log(f"❌ {tag} Token Expired.")
                    break
                
                res_data = response.json()
                msg = res_data.get("result", {}).get("message", "")
                msg_lower = msg.lower()

                # --- STOP LOGIC ---
                if "install task" in msg_lower or "complete task" in msg_lower:
                    await send_log(f"⚠️ {tag} <b>STOPPED.</b> Server requires Install Task. Switch to Option 2.")
                    break
                
                if "limit reached" in msg_lower:
                    await send_log(f"🏁 {tag} <b>FINISHED.</b> Daily limit reached.")
                    break

                if response.status_code == 200:
                    print(f"Account {no}: Claim #{count} Success")
                
                await asyncio.sleep(15)
                count += 1

        except Exception as e:
            await send_log(f"❌ {tag} Error: {str(e)}")
        finally:
            active_tasks[no] = None

# -------------------- HANDLERS -------------------- #

@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    if str(m.chat.id) != MY_CHAT_ID: return
    await m.answer("🍎 <b>Gamerush Multi-Bot Ready</b>", reply_markup=get_main_menu(), parse_mode="HTML")

@dp.message(F.text == "🏦 ACCOUNT BANK")
async def open_bank(m: types.Message):
    await m.answer("Select Account Slot:", reply_markup=get_bank_kb())

@dp.callback_query()
async def cb_handler(c: types.CallbackQuery):
    d = c.data.split("_")
    action, no = d[0], d[1] if len(d) > 1 else None

    if action == "back":
        await c.message.edit_text("Select Account Slot:", reply_markup=get_bank_kb())
    
    elif action == "view":
        token = ACCOUNTS.get(no)
        status = "READY" if token else "NO TOKEN"
        await c.message.edit_text(f"📂 <b>Slot {no}</b>\nStatus: <code>{status}</code>", reply_markup=get_acc_kb(no), parse_mode="HTML")

    elif action == "upd":
        setup_lock[c.message.chat.id] = no
        await c.message.answer(f"🔑 Send new Bearer for Account {no}:", reply_markup=ReplyKeyboardRemove())

    elif action == "claim":
        token = ACCOUNTS.get(no)
        if not token: return await c.answer("Set token first!", show_alert=True)
        if active_tasks.get(no): return await c.answer("Already running!")
        
        active_tasks[no] = asyncio.create_task(account_worker(no, token))
        await c.answer("Loop Started 🚀")

    elif action == "task":
        token = ACCOUNTS.get(no)
        if not token: return await c.answer("Set token first!", show_alert=True)
        
        async with httpx.AsyncClient(http2=True, verify=False) as client:
            res = await client.post(URL, headers=get_headers(token), json=get_payload(True))
            msg = res.json().get("result", {}).get("message", "Error")
            await c.message.answer(f"🛠 <b>[Acc {no}] Task Bypass:</b>\n{msg}", parse_mode="HTML")

    elif action == "stop":
        if active_tasks.get(no):
            active_tasks[no].cancel()
            active_tasks[no] = None
            await c.answer("Stopped.")
        else:
            await c.answer("Not running.")

@dp.message()
async def text_handler(m: types.Message):
    if m.chat.id in setup_lock:
        no = setup_lock[m.chat.id]
        token = m.text.replace("Bearer ", "").strip()
        ACCOUNTS[no] = token
        del setup_lock[m.chat.id]
        await m.answer(f"✅ Bearer saved to Slot {no}!", reply_markup=get_main_menu())

# -------------------- RUNNER -------------------- #

async def main():
    app = web.Application(); app.router.add_get("/", lambda r: web.Response(text="BOT RUNNING"))
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', PORT).start()
    print("Bot is starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
