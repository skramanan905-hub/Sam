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
# 🔥 CONFIGURATION (From your HAR) 🔥
# ==========================================
BOT_TOKEN = "8817040407:AAHxM7D7l5Cc7yuIZvpaeS7guyIzQic9fQI"
API_BASE = "https://api.pixa-ai.work"

# The EXACT token from pavo1.txt
PIXA_JWT_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxYTA2YTE2NC0zY2FjLTQzY2QtODM5YS01ZTM4ZTE2NTViZmIiLCJleHAiOjE3OTcwNDU5MDcsIm5iZiI6MTc5NDYyNjcwNywiaWF0IjoxNzk0NjI2NzA3fQ.rExyu1j6MLIMVV8Tl2RW5QBBtBTuqcgLgxAiaHof5Wo"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("PavoBot")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ==========================================
# STATE & DATA MANAGEMENT
# ==========================================
class UserStates(StatesGroup):
    waiting_for_prompt = State()
    waiting_for_image = State()

user_settings = {}

def get_settings(uid):
    if uid not in user_settings:
        user_settings[uid] = {"duration": 12, "ratio": "9:16", "image_url": None}
    return user_settings[uid]

# ==========================================
# FAKE WEB SERVER (For Render)
# ==========================================
async def web_server():
    async def handle(request):
        return web.Response(text="Pavo Bot is alive!")
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    log.info(f"Web server running on port {port}")

# ==========================================
# PAVO API CLIENT (Strictly mapped to HAR)
# ==========================================
class PavoClient:
    def __init__(self):
        self.headers = {
            "x-platform": "1", "x-user-language": "en", "x-app-timezone": "Asia/Calcutta",
            "origin": "https://app.pavo-ai.work", "referer": "https://app.pavo-ai.work/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "content-type": "application/json", "accept": "*/*",
            "authorization": f"Bearer {PIXA_JWT_TOKEN}"
        }

    async def request(self, method, endpoint, json_data=None):
        url = f"{API_BASE}{endpoint}"
        log.info(f"🌐 [API REQ] {method} {url}")
        
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, headers=self.headers, json=json_data, timeout=60) as resp:
                text = await resp.text()
                try:
                    data = json.loads(text)
                    if data.get("code") not in ("000000", None):
                        raise Exception(data.get("message", "API Error"))
                    return data.get("data", data)
                except json.JSONDecodeError:
                    raise Exception(f"Invalid JSON: {text}")

    async def get_projects(self):
        data = await self.request("GET", "/api/v1/chat/projects?page_size=10&page=1")
        return data.get("list", [])

    async def get_conversation_videos(self, conv_id):
        data = await self.request("GET", f"/api/v1/chat/conversation/history?conversation_id={conv_id}")
        videos = []
        for turn in data.get("turns", []):
            for msg in turn.get("assistant", []):
                if msg["type"] == "GenerationSuccess":
                    results = msg["data"].get("data", {}).get("results", [])
                    for res in results:
                        if res.get("url"):
                            videos.append({"url": res["url"], "prompt": msg["data"].get("prompt", "Unknown")})
        return videos

    async def upload_image(self, image_bytes, filename):
        # 1. Presigned URL
        pre_data = await self.request("POST", "/api/v1/file/presigned-url", {
            "purpose": "chat_attachment", "content_type": "image/jpeg", "filename": filename
        })
        # 2. PUT to AWS
        async with aiohttp.ClientSession() as session:
            async with session.put(pre_data["upload_url"], data=image_bytes, headers={"Content-Type": "image/jpeg"}) as resp:
                if resp.status not in (200, 201, 204): raise Exception("Failed to upload image.")
        # 3. Inspect
        await self.request("POST", "/api/v1/file/inspect", {
            "content_type": "image/jpeg", "url": pre_data["public_url"]
        })
        return pre_data["public_url"]

    async def start_video(self, prompt, duration, ratio, image_url=None):
        conv = await self.request("POST", "/api/v1/chat/conversation", {"title": prompt[:60], "folder_id": "", "kb_strict": False})
        conv_id = conv["conversation_id"]
        
        payload = {
            "conversation_id": conv_id, "prompt": prompt, "mode": "omni_to_video",
            "model": "agnes-video-new-flash", "ratio": ratio, "duration": int(duration),
            "resolution": "hd", "sound": True,
            "creative_prompt_json": json.dumps([{"type": "text", "content": prompt}]),
            "images": []
        }
        if image_url:
            payload["images"].append({"url": image_url, "meta_data": {"original_filename": "input.jpg", "content_type": "image/jpeg", "purpose": "chat_attachment"}})
        
        # SSE Stream
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
# KEYBOARDS
# ==========================================
def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Generate Video", callback_data="menu_gen")],
        [InlineKeyboardButton(text="📜 View History", callback_data="menu_history")],
        [InlineKeyboardButton(text="🔑 View Token", callback_data="menu_token")]
    ])

def settings_menu(uid):
    s = get_settings(uid)
    img_status = "✅ Image Added" if s["image_url"] else "❌ No Image (Text)"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📸 {img_status}", callback_data="set_image")],
        [InlineKeyboardButton(text=f"⏱ Duration: {s['duration']}s", callback_data="cycle_dur"), InlineKeyboardButton(text=f"📺 Ratio: {s['ratio']}", callback_data="cycle_rat")],
        [InlineKeyboardButton(text="🚀 Start Generation", callback_data="do_generate")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="menu_main")]
    ])

# ==========================================
# HANDLERS
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Welcome to Pavo AI Bot! 🚀\nEverything is mapped to your HAR data.", reply_markup=main_menu())

@dp.callback_query(F.data == "menu_main")
async def back_to_main(cb: CallbackQuery): await cb.message.edit_text("Main Menu:", reply_markup=main_menu())

@dp.callback_query(F.data == "menu_token")
async def show_token(cb: CallbackQuery): await cb.message.edit_text(f"🔑 **Active JWT:**\n`{PIXA_JWT_TOKEN}`", parse_mode="Markdown", reply_markup=main_menu())

# --- HISTORY MENU ---
@dp.callback_query(F.data == "menu_history")
async def show_history(cb: CallbackQuery):
    msg = await cb.message.edit_text("⏳ Fetching your projects...")
    client = PavoClient()
    try:
        projects = await client.get_projects()
        if not projects:
            return await msg.edit_text("No projects found.", reply_markup=main_menu())
        
        buttons = []
        for p in projects:
            if p.get("category") == "video" or p["data"].get("category") == "video":
                title = p["data"].get("title", "Untitled")[:20]
                conv_id = p["data"].get("conversation_id")
                buttons.append([InlineKeyboardButton(text=f"🎬 {title}", callback_data=f"hist_{conv_id}")])
        
        buttons.append([InlineKeyboardButton(text="⬅️ Back", callback_data="menu_main")])
        await msg.edit_text("📜 **Select a project:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}", reply_markup=main_menu())

@dp.callback_query(F.data.startswith("hist_"))
async def load_history_videos(cb: CallbackQuery):
    conv_id = cb.data.split("_")[1]
    msg = await cb.message.edit_text("⏳ Fetching videos from history...")
    client = PavoClient()
    try:
        videos = await client.get_conversation_videos(conv_id)
        if not videos:
            return await msg.edit_text("No successful videos found.", reply_markup=main_menu())
        
        await msg.edit_text(f"📦 Found {len(videos)} video(s). Sending...")
        for v in videos:
            await cb.message.answer_video(v["url"], caption=f"Prompt: {v['prompt']}")
        await cb.message.answer("End of history.", reply_markup=main_menu())
    except Exception as e:
        await msg.edit_text(f"❌ Error loading history: {e}", reply_markup=main_menu())

# --- SETTINGS MENU ---
@dp.callback_query(F.data == "menu_gen")
async def generate_menu(cb: CallbackQuery): await cb.message.edit_text("🎛 **Video Settings**", reply_markup=settings_menu(cb.from_user.id), parse_mode="Markdown")

@dp.callback_query(F.data == "cycle_dur")
async def cycle_duration(cb: CallbackQuery):
    s = get_settings(cb.from_user.id)
    durations = [4, 5, 6, 8, 10, 12]
    curr_idx = durations.index(int(s["duration"]))
    s["duration"] = durations[(curr_idx + 1) % len(durations)]
    await cb.message.edit_text("🎛 **Video Settings**", reply_markup=settings_menu(cb.from_user.id), parse_mode="Markdown")

@dp.callback_query(F.data == "cycle_rat")
async def cycle_ratio(cb: CallbackQuery):
    s = get_settings(cb.from_user.id)
    ratios = ["9:16", "16:9", "1:1", "3:4"]
    curr_idx = ratios.index(s["ratio"])
    s["ratio"] = ratios[(curr_idx + 1) % len(ratios)]
    await cb.message.edit_text("🎛 **Video Settings**", reply_markup=settings_menu(cb.from_user.id), parse_mode="Markdown")

@dp.callback_query(F.data == "set_image")
async def ask_image(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("📸 Send a photo to use as Reference (or /skip):")
    await state.set_state(UserStates.waiting_for_image)

@dp.message(UserStates.waiting_for_image, F.photo)
async def handle_image(message: Message, state: FSMContext):
    msg = await message.answer("⏳ Uploading image...")
    file = await bot.get_file(message.photo[-1].file_id)
    file_bytes = await bot.download_file(file.file_path)
    try:
        url = await PavoClient().upload_image(file_bytes.read(), "upload.jpg")
        get_settings(message.from_user.id)["image_url"] = url
        await msg.edit_text("✅ Image added!", reply_markup=settings_menu(message.from_user.id))
    except Exception as e: await msg.edit_text(f"❌ Upload failed: {e}")
    finally: await state.clear()

@dp.message(UserStates.waiting_for_image, Command("skip"))
async def skip_image(message: Message, state: FSMContext):
    get_settings(message.from_user.id)["image_url"] = None
    await message.answer("Image removed.", reply_markup=settings_menu(message.from_user.id))
    await state.clear()

# --- GENERATION ---
@dp.callback_query(F.data == "do_generate")
async def ask_prompt(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("📝 Enter your video prompt:")
    await state.set_state(UserStates.waiting_for_prompt)

@dp.message(UserStates.waiting_for_prompt)
async def process_prompt(message: Message, state: FSMContext):
    s = get_settings(message.from_user.id)
    msg = await message.answer("⏳ Generating...")
    try:
        conv_id, task_id = await PavoClient().start_video(message.text, s["duration"], s["ratio"], s["image_url"])
        await msg.edit_text(f"🎥 Task: `{task_id}`\nWaiting in queue (up to 20m)...", parse_mode="Markdown")
        
        for _ in range(120):
            await asyncio.sleep(10)
            try:
                url = await PavoClient().check_status(conv_id)
                if url:
                    await msg.edit_text("✅ Done! Uploading...")
                    await message.answer_video(url, caption=f"Prompt: {message.text}")
                    return
            except Exception as e:
                if "queue is full" in str(e).lower() or "high volume" in str(e).lower(): continue
                else: await msg.edit_text(f"❌ Failed: {e}"); return
        await msg.edit_text("⏰ Timed out.")
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")
    finally:
        await state.clear()
        get_settings(message.from_user.id)["image_url"] = None

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
