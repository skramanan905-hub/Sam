import os
import asyncio
import json
import logging
import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# ==========================================
# 🔥 HARDCODED CONFIGURATION 🔥
# ==========================================
BOT_TOKEN = "8817040407:AAHxM7D7l5Cc7yuIZvpaeS7guyIzQic9fQI"
API_BASE = "https://api.pixa-ai.work"
DB_FILE = "users.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ==========================================
# FAKE WEB SERVER FOR RENDER (STOPS RESTARTING)
# ==========================================
async def web_server():
    async def handle(request):
        return web.Response(text="Bot is running alive!")
    
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logging.info(f"Fake web server started on port {port}")

# ==========================================
# STATE MANAGEMENT & DB
# ==========================================
class UserStates(StatesGroup):
    waiting_for_email = State()
    waiting_for_password = State()
    waiting_for_prompt = State()

def load_db():
    if not os.path.exists(DB_FILE): return {}
    with open(DB_FILE, "r") as f: return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f: json.dump(data, f, indent=4)

def get_user(uid):
    return load_db().get(str(uid))

def save_user(uid, data):
    db = load_db()
    db[str(uid)] = data
    save_db(db)

# ==========================================
# PIXA API CLIENT (Same as before)
# ==========================================
class PixaClient:
    def __init__(self, token):
        self.token = token
        self.headers = {
            "x-platform": "1", "x-user-language": "en", "x-app-timezone": "Asia/Calcutta",
            "origin": "https://app.pavo-ai.work", "referer": "https://app.pavo-ai.work/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "content-type": "application/json", "accept": "*/*",
            "authorization": f"Bearer {self.token}" if self.token else ""
        }

    async def request(self, method, endpoint, json_data=None):
        async with aiohttp.ClientSession() as session:
            url = f"{API_BASE}{endpoint}"
            async with session.request(method, url, headers=self.headers, json=json_data, timeout=60) as resp:
                text = await resp.text()
                data = json.loads(text)
                if data.get("code") not in ("000000", None):
                    raise Exception(data.get("message", "API Error"))
                return data.get("data", data)

    async def register(self, email, password):
        payload = {"register_by_email": {"email": email, "password": password, "verification_code": "118348", "username": email}, "register_timezone": "Asia/Calcutta"}
        data = await self.request("POST", "/api/v1/user/register", payload)
        return data.get("access_token"), data.get("user_info", {})

    async def start_video(self, prompt, duration, ratio):
        conv = await self.request("POST", "/api/v1/chat/conversation", {"title": prompt[:60], "folder_id": "", "kb_strict": False})
        conv_id = conv["conversation_id"]
        payload = {
            "conversation_id": conv_id, "prompt": prompt, "mode": "omni_to_video",
            "model": "agnes-video-new-flash", "ratio": ratio, "duration": int(duration),
            "resolution": "hd", "sound": True,
            "creative_prompt_json": json.dumps([{"type": "text", "content": prompt}])
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{API_BASE}/api/v1/chat/stream", headers={**self.headers, "accept": "text/event-stream"}, json=payload) as resp:
                async for line in resp.content:
                    line_str = line.decode('utf-8').strip()
                    if line_str.startswith("data:"):
                        try:
                            evt = json.loads(line_str[5:].strip())
                            if evt.get("type") == "GenerationStart": return conv_id, evt.get("task_id")
                            elif evt.get("type") in ["GenerationFailed", "PromptSafetyBlocked"]: raise Exception(evt.get("data", {}).get("error", "Failed"))
                        except json.JSONDecodeError: pass
        raise Exception("Stream ended unexpectedly.")

    async def check_status(self, conv_id):
        data = await self.request("GET", f"/api/v1/chat/conversation/history?conversation_id={conv_id}")
        turns = data.get("turns", [])
        if not turns: return None
        for msg in turns[-1].get("assistant", []):
            if msg["type"] == "GenerationSuccess": return msg["data"]["data"]["results"][0]["url"]
            elif msg["type"] == "GenerationFailed": raise Exception(msg["data"].get("error", "Failed"))
        return None

# ==========================================
# KEYBOARDS & HANDLERS
# ==========================================
def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎬 Generate Video", callback_data="menu_gen")]])

def settings_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Enter Prompt", callback_data="set_prompt")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="menu_main")]
    ])

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = get_user(message.from_user.id)
    if user and user.get("token"):
        await message.answer("Welcome back! 👋", reply_markup=main_menu())
    else:
        await message.answer("Welcome! Please Register.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Register", callback_data="auth_reg")]]))

@dp.callback_query(F.data == "menu_main")
async def back_to_main(cb: CallbackQuery): await cb.message.edit_text("Main Menu:", reply_markup=main_menu())

@dp.callback_query(F.data == "auth_reg")
async def start_reg(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("Enter your Email:")
    await state.set_state(UserStates.waiting_for_email)

@dp.message(UserStates.waiting_for_email)
async def process_email(message: Message, state: FSMContext):
    await state.update_data(email=message.text.strip())
    await message.answer("Enter Password:")
    await state.set_state(UserStates.waiting_for_password)

@dp.message(UserStates.waiting_for_password)
async def process_password(message: Message, state: FSMContext):
    data = await state.get_data()
    msg = await message.answer("⏳ Registering...")
    try:
        token, _ = await PixaClient(None).register(data.get("email"), message.text.strip())
        save_user(message.from_user.id, {"email": data.get("email"), "token": token})
        await msg.edit_text("✅ Registered! Use /start")
    except Exception as e: await msg.edit_text(f"❌ Error: {e}")
    await state.clear()

@dp.callback_query(F.data == "menu_gen")
async def generate_menu(cb: CallbackQuery): await cb.message.edit_text("Settings:", reply_markup=settings_menu())

@dp.callback_query(F.data == "set_prompt")
async def ask_prompt(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("Type your video prompt:")
    await state.set_state(UserStates.waiting_for_prompt)

@dp.message(UserStates.waiting_for_prompt)
async def process_prompt(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if not user: return await message.answer("Please /start first.")
    status_msg = await message.answer("⏳ Connecting to Pixa...")
    client = PixaClient(user["token"])
    try:
        conv_id, task_id = await client.start_video(message.text, 12, "9:16")
        await status_msg.edit_text(f"🎥 Generating...\nTask: `{task_id}`")
        for _ in range(120):
            await asyncio.sleep(10)
            try:
                url = await client.check_status(conv_id)
                if url:
                    await status_msg.edit_text("✅ Done! Sending video...")
                    await message.answer_video(url, caption=f"Prompt: {message.text}")
                    return
            except Exception as e:
                if "queue is full" in str(e).lower() or "high volume" in str(e).lower(): continue
                else:
                    await status_msg.edit_text(f"❌ Failed: {e}")
                    return
        await status_msg.edit_text("⏰ Timed out.")
    except Exception as e: await status_msg.edit_text(f"❌ Error: {e}")
    finally: await state.clear()

# ==========================================
# MAIN EXECUTION
# ==========================================
async def main():
    # Start the fake web server for Render
    await web_server()
    # Start the Telegram Bot
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
