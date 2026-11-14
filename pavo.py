import os
import asyncio
import json
import logging
import aiohttp
import random
import string
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

BOT_TOKEN = os.getenv("8817040407:AAHxM7D7l5Cc7yuIZvpaeS7guyIzQic9fQI")
API_BASE = os.getenv("DEFAULT_API_BASE", "https://api.pixa-ai.work")
DB_FILE = "users.json"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# --- State Management for User Inputs ---
class UserStates(StatesGroup):
    waiting_for_email = State()
    waiting_for_password = State()
    waiting_for_prompt = State()

# --- Local JSON Database ---
def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_user(uid):
    db = load_db()
    return db.get(str(uid))

def save_user(uid, data):
    db = load_db()
    db[str(uid)] = data
    save_db(db)

# --- Pixa API Client ---
class PixaClient:
    def __init__(self, token):
        self.token = token
        self.headers = {
            "x-platform": "1",
            "x-user-language": "en",
            "x-app-timezone": "Asia/Calcutta",
            "origin": "https://app.pavo-ai.work",
            "referer": "https://app.pavo-ai.work/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "content-type": "application/json",
            "accept": "*/*",
            "authorization": f"Bearer {self.token}" if self.token else ""
        }

    async def request(self, method, endpoint, json_data=None):
        async with aiohttp.ClientSession() as session:
            url = f"{API_BASE}{endpoint}"
            async with session.request(method, url, headers=self.headers, json=json_data, timeout=60) as resp:
                text = await resp.text()
                try:
                    data = json.loads(text)
                    if data.get("code") not in ("000000", None):
                        raise Exception(data.get("message", "API Error"))
                    return data.get("data", data)
                except json.JSONDecodeError:
                    raise Exception(f"HTTP {resp.status}: Invalid response")

    async def register(self, email, password):
        payload = {
            "register_by_email": {
                "email": email, "password": password,
                "verification_code": "118348", # Standard bypass from HAR
                "username": email
            },
            "register_timezone": "Asia/Calcutta"
        }
        data = await self.request("POST", "/api/v1/user/register", payload)
        return data.get("access_token"), data.get("user_info", {})

    async def get_history(self):
        # 1. Get projects
        proj_data = await self.request("GET", "/api/v1/chat/projects?page_size=30&page=1")
        projects = proj_data.get("list", [])
        return projects

    async def start_video(self, prompt, duration, ratio):
        # 1. Create Conversation
        conv = await self.request("POST", "/api/v1/chat/conversation", {
            "title": prompt[:60], "folder_id": "", "kb_strict": False
        })
        conv_id = conv["conversation_id"]

        # 2. Start SSE Stream (we just read until GenerationStart)
        payload = {
            "conversation_id": conv_id,
            "prompt": prompt,
            "mode": "omni_to_video",
            "model": "agnes-video-new-flash",
            "ratio": ratio,
            "duration": int(duration),
            "resolution": "hd",
            "sound": True,
            "creative_prompt_json": json.dumps([{"type": "text", "content": prompt}])
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(f"{API_BASE}/api/v1/chat/stream", headers={**self.headers, "accept": "text/event-stream"}, json=payload) as resp:
                async for line in resp.content:
                    line_str = line.decode('utf-8').strip()
                    if line_str.startswith("data:"):
                        try:
                            evt = json.loads(line_str[5:].strip())
                            if evt.get("type") == "GenerationStart":
                                return conv_id, evt.get("task_id")
                            elif evt.get("type") == "GenerationFailed":
                                raise Exception(evt.get("data", {}).get("error", "Generation Failed"))
                            elif evt.get("type") == "PromptSafetyBlocked":
                                raise Exception(evt.get("data", {}).get("error", "Text Rejected"))
                        except json.JSONDecodeError:
                            pass
        raise Exception("Stream ended unexpectedly.")

    async def check_status(self, conv_id):
        data = await self.request("GET", f"/api/v1/chat/conversation/history?conversation_id={conv_id}")
        turns = data.get("turns", [])
        if not turns: return None
        for msg in turns[-1].get("assistant", []):
            if msg["type"] == "GenerationSuccess":
                return msg["data"]["data"]["results"][0]["url"]
            elif msg["type"] == "GenerationFailed":
                raise Exception(msg["data"].get("error", "Failed"))
        return None


# --- Keyboards ---
def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Generate Video", callback_data="menu_gen")],
        [InlineKeyboardButton(text="📜 Video History", callback_data="menu_history")],
        [InlineKeyboardButton(text="👤 Account Info", callback_data="menu_acc")]
    ])

def settings_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Enter Prompt", callback_data="set_prompt")],
        [InlineKeyboardButton(text="⏱ Duration: 12s", callback_data="ignore"), InlineKeyboardButton(text="📺 Ratio: 9:16", callback_data="ignore")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="menu_main")]
    ])

# --- Handlers ---
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = get_user(message.from_user.id)
    if user and user.get("token"):
        await message.answer("Welcome back! 👋 What would you like to do?", reply_markup=main_menu())
    else:
        await message.answer("Welcome to Pixa AI Bot! 🚀\nTo get started, please **Login** or **Register** using the buttons below.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Register", callback_data="auth_reg")],
            [InlineKeyboardButton(text="Login", callback_data="auth_log")]
        ]))

@dp.callback_query(F.data == "menu_main")
async def back_to_main(cb: CallbackQuery):
    await cb.message.edit_text("Main Menu:", reply_markup=main_menu())

@dp.callback_query(F.data == "auth_reg")
async def start_reg(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("Please enter your **Email** for registration:")
    await state.set_state(UserStates.waiting_for_email)

@dp.message(UserStates.waiting_for_email)
async def process_email(message: Message, state: FSMContext):
    email = message.text.strip()
    await state.update_data(email=email)
    await message.answer("Now enter a **Password** for your account:")
    await state.set_state(UserStates.waiting_for_password)

@dp.message(UserStates.waiting_for_password)
async def process_password(message: Message, state: FSMContext):
    password = message.text.strip()
    data = await state.get_data()
    email = data.get("email")
    
    msg = await message.answer("⏳ Registering...")
    client = PixaClient(token=None)
    try:
        token, info = await client.register(email, password)
        save_user(message.from_user.id, {"email": email, "token": token})
        await msg.edit_text("✅ Registration successful! /start to view menu.")
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")
    await state.clear()

@dp.callback_query(F.data == "menu_gen")
async def generate_menu(cb: CallbackQuery):
    await cb.message.edit_text("Video Generation Settings:\n(Model: Agnes 2.5 Flash - HD)", reply_markup=settings_menu())

@dp.callback_query(F.data == "set_prompt")
async def ask_prompt(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("Please type your video prompt now (e.g., 'Girl dancing in neon city'):")
    await state.set_state(UserStates.waiting_for_prompt)

@dp.message(UserStates.waiting_for_prompt)
async def process_prompt(message: Message, state: FSMContext):
    prompt = message.text
    user = get_user(message.from_user.id)
    if not user:
        return await message.answer("Please /start and login first.")

    status_msg = await message.answer("⏳ Connecting to Pixa AI...")
    client = PixaClient(user["token"])
    
    try:
        conv_id, task_id = await client.start_video(prompt, duration=12, ratio="9:16")
        await status_msg.edit_text(f"🎥 Generating Video...\nTask: `{task_id}`\n\n⚠️ Note: Free queues can take 5-15 minutes. Please wait.")
        
        # Polling
        for _ in range(120): # 10 mins max
            await asyncio.sleep(10)
            try:
                url = await client.check_status(conv_id)
                if url:
                    await status_msg.edit_text("✅ Generation Complete! Sending video...")
                    await message.answer_video(url, caption=f"Prompt: {prompt}")
                    return
            except Exception as e:
                if "queue is full" in str(e):
                    continue # keep polling
                else:
                    await status_msg.edit_text(f"❌ Failed: {e}")
                    return
        await status_msg.edit_text("⏰ Timed out. The server queue is too busy. Please try again later.")
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {e}")
    finally:
        await state.clear()

@dp.callback_query(F.data == "menu_history")
async def show_history(cb: CallbackQuery):
    user = get_user(cb.from_user.id)
    if not user:
        return await cb.answer("Please /start and login.")
        
    await cb.message.edit_text("⏳ Fetching history...")
    client = PixaClient(user["token"])
    try:
        projects = await client.get_history()
        if not projects:
            return await cb.message.edit_text("No generation history found.", reply_markup=main_menu())
        
        text = "📜 **Recent Video History:**\n\n"
        for i, p in enumerate(projects[:5]):
            title = p["data"].get("title", "Untitled")[:20]
            status = p["data"].get("status", "unknown")
            text += f"{i+1}. {title} — Status: `{status}`\n"
            
        await cb.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Back", callback_data="menu_main")]
        ]))
    except Exception as e:
        await cb.message.edit_text(f"Error fetching history: {e}", reply_markup=main_menu())

async def main():
    print("Bot started...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
