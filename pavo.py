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
# 🔥 CONFIGURATION 🔥
# ==========================================
BOT_TOKEN = "8817040407:AAHxM7D7l5Cc7yuIZvpaeS7guyIzQic9fQI"

# 🔑 THIS IS THE TOKEN FROM YOUR HAR FILE (pavo1.txt)
PIXA_JWT_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxYTA2YTE2NC0zY2FjLTQzY2QtODM5YS01ZTM4ZTE2NTViZmIiLCJleHAiOjE3OTcwNDU5MDcsIm5iZiI6MTc5NDYyNjcwNywiaWF0IjoxNzk0NjI2NzA3fQ.rExyu1j6MLIMVV8Tl2RW5QBBtBTuqcgLgxAiaHof5Wo"

API_BASE = "https://api.pixa-ai.work"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("PixaBot")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ==========================================
# STATE MANAGEMENT
# ==========================================
class UserStates(StatesGroup):
    waiting_for_prompt = State()

# ==========================================
# FAKE WEB SERVER (For Render)
# ==========================================
async def web_server():
    async def handle(request):
        return web.Response(text="Bot is running!")
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    log.info(f"Web server running on port {port}")

# ==========================================
# PIXA API CLIENT (No Login Needed)
# ==========================================
class PixaClient:
    def __init__(self):
        self.headers = {
            "x-platform": "1", "x-user-language": "en", "x-app-timezone": "Asia/Calcutta",
            "origin": "https://app.pavo-ai.work", "referer": "https://app.pavo-ai.work/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "content-type": "application/json", "accept": "*/*",
            "authorization": f"Bearer {PIXA_JWT_TOKEN}"  # Using the hardcoded token!
        }

    async def request(self, method, endpoint, json_data=None):
        url = f"{API_BASE}{endpoint}"
        log.info(f"🌐 [RAW REQ] {method} {url}")
        if json_data: log.info(f"📦 [PAYLOAD] {json.dumps(json_data)}")

        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, headers=self.headers, json=json_data, timeout=60) as resp:
                text = await resp.text()
                log.info(f"✅ [RAW RES] {resp.status} | {text}")
                try:
                    data = json.loads(text)
                    if data.get("code") not in ("000000", None):
                        raise Exception(data.get("message", "API Error"))
                    return data.get("data", data)
                except json.JSONDecodeError:
                    raise Exception(f"Invalid response format: {text}")

    async def start_video(self, prompt, duration=12, ratio="9:16"):
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
                            log.info(f"📡 [STREAM EVT] {evt.get('type')}")
                            if evt.get("type") == "GenerationStart": 
                                return conv_id, evt.get("task_id")
                            elif evt.get("type") in ["GenerationFailed", "PromptSafetyBlocked"]: 
                                raise Exception(evt.get("data", {}).get("error", "Generation Failed"))
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

# ==========================================
# KEYBOARDS
# ==========================================
def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Generate Video", callback_data="menu_gen")],
        [InlineKeyboardButton(text="👤 View Token", callback_data="menu_token")]
    ])

def settings_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Enter Prompt", callback_data="set_prompt")],
        [InlineKeyboardButton(text="⏱ Duration: 12s", callback_data="ignore")],
        [InlineKeyboardButton(text="📺 Ratio: 9:16", callback_data="ignore")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="menu_main")]
    ])

# ==========================================
# HANDLERS
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Welcome! 🚀 Ready to generate videos using the Pavo AI token.", reply_markup=main_menu())

@dp.callback_query(F.data == "menu_main")
async def back_to_main(cb: CallbackQuery): 
    await cb.message.edit_text("Main Menu:", reply_markup=main_menu())

@dp.callback_query(F.data == "menu_token")
async def show_token(cb: CallbackQuery):
    await cb.message.edit_text(
        f"🔑 **Active Token (from pavo1.txt):**\n\n`{PIXA_JWT_TOKEN}`\n\n(Expires: Dec 11, 2026)", 
        parse_mode="Markdown", 
        reply_markup=main_menu()
    )

@dp.callback_query(F.data == "menu_gen")
async def generate_menu(cb: CallbackQuery):
    await cb.message.edit_text("Video Generation Settings:\n(Model: Agnes 2.5 Flash - HD)", reply_markup=settings_menu())

@dp.callback_query(F.data == "set_prompt")
async def ask_prompt(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("Please type your video prompt now:")
    await state.set_state(UserStates.waiting_for_prompt)

@dp.message(UserStates.waiting_for_prompt)
async def process_prompt(message: Message, state: FSMContext):
    status_msg = await message.answer("⏳ Connecting to Pavo AI...")
    client = PixaClient()
    
    try:
        conv_id, task_id = await client.start_video(message.text, duration=12, ratio="9:16")
        await status_msg.edit_text(f"🎥 Generating Video...\nTask: `{task_id}`\n\n⚠️ Queue can take 5-15 mins.")
        
        # Queue handling loop
        for _ in range(120): 
            await asyncio.sleep(10)
            try:
                url = await client.check_status(conv_id)
                if url:
                    await status_msg.edit_text("✅ Generation Complete! Uploading...")
                    await message.answer_video(url, caption=f"Prompt: {message.text}")
                    return
            except Exception as e:
                if "queue is full" in str(e).lower() or "high volume" in str(e).lower():
                    continue 
                else:
                    await status_msg.edit_text(f"❌ API Error: {e}")
                    return
        await status_msg.edit_text("⏰ Timed out (10 minutes).")
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {e}")
    finally:
        await state.clear()

# ==========================================
# MAIN EXECUTION
# ==========================================
async def main():
    await web_server()
    await bot.delete_webhook(drop_pending_updates=True)
    log.info("Bot polling started...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
