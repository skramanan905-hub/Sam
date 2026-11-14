import os
import asyncio
import json
import logging
import random
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
API_BASE = "https://api.pixa-ai.work"
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
    waiting_for_edit_prompt = State()
    waiting_for_mass_prompt = State()

user_settings = {}
video_cache = {}

def get_settings(uid):
    if uid not in user_settings:
        user_settings[uid] = {"duration": 12, "ratio": "9:16", "image_url": None, "conversation_id": None, "mass_amount": 15}
    return user_settings[uid]

# ==========================================
# FAKE WEB SERVER (Render)
# ==========================================
async def web_server():
    async def handle(request): return web.Response(text="Pavo Bot is alive!")
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

# ==========================================
# PAVO API CLIENT
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
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, headers=self.headers, json=json_data, timeout=60) as resp:
                text = await resp.text()
                try:
                    data = json.loads(text)
                    if data.get("code") not in ("000000", None): raise Exception(data.get("message", "API Error"))
                    return data.get("data", data)
                except json.JSONDecodeError: raise Exception(f"Invalid JSON: {text}")

    async def get_projects(self):
        data = await self.request("GET", "/api/v1/chat/projects?page_size=50&page=1")
        return data.get("list", [])

    async def get_conversation_videos(self, conv_id):
        data = await self.request("GET", f"/api/v1/chat/conversation/history?conversation_id={conv_id}")
        videos = []
        for turn in data.get("turns", []):
            prompt_text = "Unknown"
            for user_msg in turn.get("user", []):
                if user_msg["type"] == "Message" and "content" in user_msg.get("data", {}):
                    prompt_text = user_msg["data"]["content"]
                    break
            for msg in turn.get("assistant", []):
                if msg["type"] == "GenerationSuccess":
                    results = msg["data"].get("data", {}).get("results", [])
                    duration, ratio = 12, "9:16"
                    for a_msg in turn.get("assistant", []):
                        if a_msg["type"] == "GenerationStart":
                            duration = a_msg["data"].get("duration", 12)
                            ratio = a_msg["data"].get("ratio", "9:16")
                            break
                    for res in results:
                        if res.get("url"):
                            videos.append({"url": res["url"], "prompt": prompt_text, "duration": duration, "ratio": ratio, "conv_id": conv_id, "image_url": None})
        return videos

    async def upload_image(self, image_bytes, filename):
        pre_data = await self.request("POST", "/api/v1/file/presigned-url", {"purpose": "chat_attachment", "content_type": "image/jpeg", "filename": filename})
        async with aiohttp.ClientSession() as session:
            async with session.put(pre_data["upload_url"], data=image_bytes, headers={"Content-Type": "image/jpeg"}) as resp:
                if resp.status not in (200, 201, 204): raise Exception("Failed to upload image.")
        await self.request("POST", "/api/v1/file/inspect", {"content_type": "image/jpeg", "url": pre_data["public_url"]})
        return pre_data["public_url"]

    async def start_video(self, prompt, duration, ratio, image_url=None, existing_conv_id=None):
        conv_id = existing_conv_id
        if not conv_id:
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
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{API_BASE}/api/v1/chat/stream", headers={**self.headers, "accept": "text/event-stream"}, json=payload) as resp:
                async for line in resp.content:
                    line_str = line.decode('utf-8').strip()
                    if line_str.startswith("data:"):
                        try:
                            evt = json.loads(line_str[5:].strip())
                            if evt.get("type") == "GenerationStart": return conv_id, evt.get("task_id")
                            elif evt.get("type") in ["GenerationFailed", "PromptSafetyBlocked"]: raise Exception(evt.get("data", {}).get("error_message", "Failed"))
                        except json.JSONDecodeError: pass
        raise Exception("Stream ended unexpectedly.")

    async def check_status(self, conv_id, current_task_id):
        try:
            data = await self.request("GET", f"/api/v1/chat/conversation/history?conversation_id={conv_id}")
            turns = data.get("turns", [])
            if not turns: return None
            last_turn = turns[-1]
            for msg in last_turn.get("assistant", []):
                if msg["type"] == "GenerationSuccess" and msg["data"].get("task_id") == current_task_id:
                    return msg["data"]["data"]["results"][0]["url"]
                elif msg["type"] == "GenerationFailed" and msg["data"].get("task_id") == current_task_id:
                    raise Exception(msg["data"].get("error_message", "Generation Failed"))
            return None
        except Exception as e:
            raise e

# ==========================================
# KEYBOARDS
# ==========================================
def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Generate New Video", callback_data="menu_gen")],
        [InlineKeyboardButton(text="🚀 Mass Generate (Spam Mode)", callback_data="menu_mass")],
        [InlineKeyboardButton(text="📜 Search All History", callback_data="menu_all_history")]
    ])

def settings_menu(uid):
    s = get_settings(uid)
    img_status = "✅ Image Added" if s["image_url"] else "❌ No Image"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📸 {img_status}", callback_data="set_image")],
        [InlineKeyboardButton(text=f"⏱ Duration: {s['duration']}s", callback_data="cycle_dur"), InlineKeyboardButton(text=f"📺 Ratio: {s['ratio']}", callback_data="cycle_rat")],
        [InlineKeyboardButton(text="🚀 Start Generation", callback_data="do_generate")],
        [InlineKeyboardButton(text="⬅️ Back to Main Menu", callback_data="menu_main")]
    ])

def mass_settings_menu(uid):
    s = get_settings(uid)
    img_status = "✅ Image Added" if s["image_url"] else "❌ No Image"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📸 {img_status}", callback_data="set_image")],
        [InlineKeyboardButton(text=f"💥 Threads: {s['mass_amount']}x", callback_data="cycle_mass_amt")],
        [InlineKeyboardButton(text=f"⏱ Duration: {s['duration']}s", callback_data="cycle_dur"), InlineKeyboardButton(text=f"📺 Ratio: {s['ratio']}", callback_data="cycle_rat")],
        [InlineKeyboardButton(text="💣 Start Mass Spam", callback_data="do_mass_generate")],
        [InlineKeyboardButton(text="⬅️ Back to Main Menu", callback_data="menu_main")]
    ])

def video_action_keyboard(vid_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Edit again", callback_data=f"edit_{vid_id}"), InlineKeyboardButton(text="🔄 Regenerate", callback_data=f"regen_{vid_id}")]
    ])

# ==========================================
# WORKER: Generates & Polls 1 Video
# ==========================================
async def background_worker(message: Message, prompt: str, duration: int, ratio: str, image_url: str):
    client = PavoClient()
    try:
        conv_id, task_id = await client.start_video(prompt, duration, ratio, image_url)
    except Exception:
        return
    
    wait_time = 0
    while wait_time < 1200:
        await asyncio.sleep(15)
        wait_time += 15
        try:
            url = await client.check_status(conv_id, task_id)
            if url:
                vid_id = str(random.randint(10000, 99999))
                video_cache[vid_id] = {"prompt": prompt, "duration": duration, "ratio": ratio, "image_url": image_url, "conv_id": conv_id}
                kb = video_action_keyboard(vid_id)
                await message.answer_video(url, caption=f"✅ **Mass Gen Success!**\nPrompt: {prompt}\nDuration: {duration}s | Ratio: {ratio}", reply_markup=kb, parse_mode="Markdown")
                return
        except Exception as e:
            if "queue is full" in str(e).lower() or "high volume" in str(e).lower(): continue
            else: return

async def single_generation(message: Message, prompt: str, duration: int, ratio: str, image_url: str, conv_id: str):
    msg = await message.answer(f"⏳ Generating {duration}s video ({ratio})...")
    try:
        new_conv_id, task_id = await PavoClient().start_video(prompt, duration, ratio, image_url, conv_id)
        await msg.edit_text(f"🎥 Task: `{task_id}`\n\n⚠️ Queue can be full. Waiting...", parse_mode="Markdown")
        
        wait_time = 0
        while wait_time < 1200:
            await asyncio.sleep(10)
            wait_time += 10
            try:
                url = await PavoClient().check_status(new_conv_id, task_id)
                if url:
                    await msg.edit_text("✅ Done! Uploading...")
                    vid_id = str(random.randint(10000, 99999))
                    video_cache[vid_id] = {"prompt": prompt, "duration": duration, "ratio": ratio, "image_url": image_url, "conv_id": new_conv_id}
                    await message.answer_video(url, caption=f"Prompt: {prompt}\nDuration: {duration}s | Ratio: {ratio}", reply_markup=video_action_keyboard(vid_id))
                    return
            except Exception as e:
                if "queue is full" in str(e).lower() or "high volume" in str(e).lower():
                    if wait_time % 60 == 0:
                        await msg.edit_text(f"⏳ **Queue is Full**\n(Waiting {wait_time}s...)", parse_mode="HTML")
                    continue
                else:
                    await msg.edit_text(f"❌ **Generation Failed:**\n\n{e}")
                    return
        await msg.edit_text("⏰ Timed out.")
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")

# ==========================================
# HANDLERS
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    get_settings(message.from_user.id)["conversation_id"] = None
    await message.answer("Welcome to Pavo AI Bot! 🚀\nChoose an option:", reply_markup=main_menu())

@dp.callback_query(F.data == "menu_main")
async def back_to_main(cb: CallbackQuery, state: FSMContext): 
    await state.clear()
    await cb.message.edit_text("Main Menu:", reply_markup=main_menu())

# --- GLOBAL HISTORY SEARCH ---
@dp.callback_query(F.data == "menu_all_history")
async def search_all_history(cb: CallbackQuery):
    msg = await cb.message.edit_text("🔍 Scanning all your projects for videos... (This might take a minute)")
    client = PavoClient()
    try:
        projects = await client.get_projects()
        if not projects: return await msg.edit_text("No projects found.", reply_markup=main_menu())
        
        total_videos = 0
        await msg.edit_text(f"🔍 Scanning {len(projects)} projects...")
        
        for p in projects:
            if p.get("category") == "video" or p["data"].get("category") == "video":
                conv_id = p["data"].get("conversation_id")
                videos = await client.get_conversation_videos(conv_id)
                if videos:
                    for v in videos:
                        total_videos += 1
                        vid_id = str(random.randint(10000, 99999))
                        video_cache[vid_id] = v
                        await cb.message.answer_video(v["url"], caption=f"Prompt: {v['prompt']}\nDuration: {v['duration']}s | Ratio: {v['ratio']}", reply_markup=video_action_keyboard(vid_id))
        
        if total_videos == 0:
            await cb.message.answer("No videos found in your entire history.")
            
        back_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Back to Main Menu", callback_data="menu_main")]])
        await cb.message.answer(f"✅ Scan complete! Found {total_videos} videos.", reply_markup=back_kb)
    except Exception as e:
        await cb.message.answer(f"❌ Error: {e}", reply_markup=main_menu())

# --- MASS GENERATION (SPAM MODE) ---
@dp.callback_query(F.data == "menu_mass")
async def mass_menu(cb: CallbackQuery): 
    await cb.message.edit_text("🚀 **Mass Generation (Spam Mode)**\n\nBecause the queue is often full, we will fire multiple requests at the exact same time. Whichever one gets through the queue will generate.\n\nConfigure below:", reply_markup=mass_settings_menu(cb.from_user.id), parse_mode="Markdown")

@dp.callback_query(F.data == "cycle_mass_amt")
async def cycle_mass_amt(cb: CallbackQuery):
    s = get_settings(cb.from_user.id)
    amounts = [5, 10, 15, 20, 30]
    curr_idx = amounts.index(s["mass_amount"])
    s["mass_amount"] = amounts[(curr_idx + 1) % len(amounts)]
    await cb.message.edit_text("🚀 **Mass Generation (Spam Mode)**", reply_markup=mass_settings_menu(cb.from_user.id), parse_mode="Markdown")

@dp.callback_query(F.data == "do_mass_generate")
async def ask_mass_prompt(cb: CallbackQuery, state: FSMContext):
    s = get_settings(cb.from_user.id)
    await cb.message.edit_text(f"📝 Enter your prompt. It will be sent **{s['mass_amount']} times** simultaneously:\n\n/start to cancel.", parse_mode="Markdown")
    await state.set_state(UserStates.waiting_for_mass_prompt)

@dp.message(UserStates.waiting_for_mass_prompt)
async def process_mass_prompt(message: Message, state: FSMContext):
    if message.text == "/start":
        await state.clear()
        return await message.answer("Cancelled.", reply_markup=main_menu())
        
    s = get_settings(message.from_user.id)
    await message.answer(f"💣 **Firing {s['mass_amount']} generation threads simultaneously!**\n\nPlease wait. Whichever one gets through the queue will be sent to you as a video. Do not close the chat.")
    
    for _ in range(s["mass_amount"]):
        asyncio.create_task(background_worker(message, message.text, s["duration"], s["ratio"], s["image_url"]))
        await asyncio.sleep(0.5)
        
    await state.clear()

# --- NORMAL FLOW ---
@dp.callback_query(F.data == "menu_gen")
async def generate_menu(cb: CallbackQuery): 
    get_settings(cb.from_user.id)["conversation_id"] = None
    await cb.message.edit_text("🎛 **Video Settings**", reply_markup=settings_menu(cb.from_user.id), parse_mode="Markdown")

@dp.callback_query(F.data == "cycle_dur")
async def cycle_duration(cb: CallbackQuery):
    s = get_settings(cb.from_user.id)
    durations = [4, 5, 6, 8, 10, 12]
    curr_idx = durations.index(int(s["duration"]))
    s["duration"] = durations[(curr_idx + 1) % len(durations)]
    await cb.message.edit_text(f"🎛 **Video Settings**\nDuration changed to **{s['duration']}s**", reply_markup=settings_menu(cb.from_user.id), parse_mode="Markdown")

@dp.callback_query(F.data == "cycle_rat")
async def cycle_ratio(cb: CallbackQuery):
    s = get_settings(cb.from_user.id)
    ratios = ["9:16", "16:9", "1:1", "3:4"]
    curr_idx = ratios.index(s["ratio"])
    s["ratio"] = ratios[(curr_idx + 1) % len(ratios)]
    await cb.message.edit_text(f"🎛 **Video Settings**\nRatio changed to **{s['ratio']}**", reply_markup=settings_menu(cb.from_user.id), parse_mode="Markdown")

@dp.callback_query(F.data == "set_image")
async def ask_image(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("📸 Send a photo to use as Reference (or /skip):\n\n/start to cancel.")
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

@dp.callback_query(F.data == "do_generate")
async def ask_prompt(cb: CallbackQuery, state: FSMContext):
    s = get_settings(cb.from_user.id)
    await cb.message.edit_text(f"📝 Enter your video prompt (Duration: {s['duration']}s | Ratio: {s['ratio']}):\n\n/start to cancel.")
    await state.set_state(UserStates.waiting_for_prompt)

@dp.message(UserStates.waiting_for_prompt)
async def process_prompt(message: Message, state: FSMContext):
    if message.text == "/start":
        await state.clear()
        return await message.answer("Cancelled.", reply_markup=main_menu())
        
    s = get_settings(message.from_user.id)
    await single_generation(message, message.text, s["duration"], s["ratio"], s["image_url"], s["conversation_id"])
    await state.clear()

# --- EDIT & REGENERATE ---
@dp.callback_query(F.data.startswith("regen_"))
async def regenerate_video(cb: CallbackQuery):
    vid_id = cb.data.split("_")[1]
    v = video_cache.get(vid_id)
    if not v: return await cb.answer("Video data expired.", show_alert=True)
    await cb.message.edit_reply_markup(reply_markup=None)
    await single_generation(cb.message, v["prompt"], v["duration"], v["ratio"], v["image_url"], v["conv_id"])

@dp.callback_query(F.data.startswith("edit_"))
async def edit_video(cb: CallbackQuery, state: FSMContext):
    vid_id = cb.data.split("_")[1]
    v = video_cache.get(vid_id)
    if not v: return await cb.answer("Video data expired.", show_alert=True)
    
    await state.update_data(edit_data=v)
    await cb.message.reply(f"✏️ **Editing Prompt**\n\nOriginal: `{v['prompt']}`\n\nPlease type your new prompt:\n\n/start to cancel.", parse_mode="Markdown")
    await state.set_state(UserStates.waiting_for_edit_prompt)

@dp.message(UserStates.waiting_for_edit_prompt)
async def process_edit_prompt(message: Message, state: FSMContext):
    if message.text == "/start":
        await state.clear()
        return await message.answer("Cancelled.", reply_markup=main_menu())
        
    data = await state.get_data()
    v = data.get("edit_data")
    if not v: return await message.answer("Error: Data lost.")
    await single_generation(message, message.text, v["duration"], v["ratio"], v["image_url"], v["conv_id"])
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
