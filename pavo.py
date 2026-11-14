import os
import asyncio
import json
import logging
import random
import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

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
            image_url = None
            for user_msg in turn.get("user", []):
                if user_msg.get("type") == "Message" and "content" in user_msg.get("data", {}):
                    prompt_text = user_msg["data"]["content"]
                elif user_msg.get("type") == "File":
                    image_url = user_msg["data"].get("url")
                elif user_msg.get("type") == "creative_prompt":
                    try:
                        cp_json = json.loads(user_msg["data"].get("creative_prompt_json", "[]"))
                        if cp_json and "content" in cp_json[0]: prompt_text = cp_json[0]["content"]
                    except: pass
            
            for msg in turn.get("assistant", []):
                if msg["type"] == "GenerationSuccess":
                    results = msg["data"].get("data", {}).get("results", [])
                    duration, ratio = 12, "9:16"
                    for a_msg in turn.get("assistant", []):
                        if a_msg["type"] == "GenerationStart":
                            duration = a_msg["data"].get("duration", 12)
                            ratio = a_msg["data"].get("ratio", "9:16")
                            if a_msg["data"].get("prompt"): prompt_text = a_msg["data"]["prompt"]
                            break
                    for res in results:
                        if res.get("url"):
                            videos.append({"url": res["url"], "prompt": prompt_text, "duration": duration, "ratio": ratio, "conv_id": conv_id, "image_url": image_url})
        return videos

    async def upload_image(self, image_bytes, filename):
        pre_data = await self.request("POST", "/api/v1/file/presigned-url", {"purpose": "chat_attachment", "content_type": "image/jpeg", "filename": filename})
        async with aiohttp.ClientSession() as session:
            async with session.put(pre_data["upload_url"], data=image_bytes, headers={"Content-Type": "image/jpeg"}) as resp:
                if resp.status not in (200, 201, 204): raise Exception("Failed to upload image.")
        await self.request("POST", "/api/v1/file/inspect", {"content_type": "image/jpeg", "url": pre_data["public_url"]})
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

# ==========================================
# WEB API ENDPOINTS
# ==========================================
async def index_handler(request):
    # Ensure index.html exists in the same folder
    if not os.path.exists('index.html'):
        return web.Response(text="Error: index.html not found in repository!", status=404)
    return web.FileResponse('./index.html')

async def health_check(request):
    return web.Response(text="OK")

async def api_history(request):
    client = PavoClient()
    try:
        projects = await client.get_projects()
        return web.json_response({"status": "success", "projects": projects})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)})

async def api_videos(request):
    conv_id = request.query.get('conv_id')
    client = PavoClient()
    try:
        videos = await client.get_conversation_videos(conv_id)
        return web.json_response({"status": "success", "videos": videos})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)})

async def api_upload(request):
    reader = await request.multipart()
    field = await reader.next()
    if not field: return web.json_response({"status": "error", "message": "No file"})
    
    image_bytes = await field.read()
    client = PavoClient()
    try:
        url = await client.upload_image(image_bytes, "upload.jpg")
        return web.json_response({"status": "success", "url": url})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)})

async def api_generate(request):
    try:
        data = await request.json()
        prompt = data.get("prompt")
        duration = data.get("duration", 12)
        ratio = data.get("ratio", "9:16")
        image_url = data.get("image_url")
        chat_id = data.get("chat_id")
        
        client = PavoClient()
        conv_id, task_id = await client.start_video(prompt, duration, ratio, image_url)
        
        asyncio.create_task(monitor_and_notify(conv_id, task_id, prompt, chat_id))
        
        return web.json_response({"status": "success", "task_id": task_id})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)})

async def monitor_and_notify(conv_id, task_id, prompt, chat_id):
    client = PavoClient()
    wait_time = 0
    while wait_time < 1200:
        await asyncio.sleep(15)
        wait_time += 15
        try:
            url = await client.check_status(conv_id, task_id)
            if url:
                if chat_id:
                    await bot.send_video(chat_id, url, caption=f"✅ Video Ready!\nPrompt: {prompt}")
                return
        except Exception:
            pass

# ==========================================
# TELEGRAM BOT SETUP
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: Message):
    # 🔥 HERE IS THE URL 🔥
    url = "https://sam-8-7lpn.onrender.com"
    
    # Telegram WebApp requires HTTPS
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎬 Open Pavo AI App", web_app=web.WebAppInfo(url=url))]])
    await message.answer("Welcome! Click below to open the full Pavo AI interface directly in Telegram:", reply_markup=kb)

# ==========================================
# MAIN
# ==========================================
async def main():
    app = web.Application()
    app.router.add_get('/', index_handler)
    app.router.add_get('/health', health_check) # Render Health Check
    app.router.add_get('/api/history', api_history)
    app.router.add_get('/api/videos', api_videos)
    app.router.add_post('/api/upload', api_upload)
    app.router.add_post('/api/generate', api_generate)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Render assigns a PORT dynamically. We MUST bind to it.
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    log.info(f"✅ Web server successfully bound to port {port}")
    
    await bot.delete_webhook(drop_pending_updates=True)
    log.info("🤖 Telegram Bot polling started...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
