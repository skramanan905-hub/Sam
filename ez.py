import os
import json
import time
import uuid
import logging
import threading

import telebot
from curl_cffi import requests as curl_requests

BOT_TOKEN = os.environ["8890014279:AAGuKNVfg2WJ21DXCS_kBXgVlexjRxXUhL8"]          # never hardcode this
BASE_URL = "https://magichour.ai"
POLL_INTERVAL = 4
MAX_WAIT_SECONDS = 600
PENDING_TTL = 600
MAX_IMAGE_BYTES = 10 * 1024 * 1024

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("magic-bot")

bot = telebot.TeleBot(BOT_TOKEN, threaded=True, num_threads=8)

pending: dict[int, tuple[bytes, float]] = {}
pending_lock = threading.Lock()


def new_session() -> curl_requests.Session:
    session = curl_requests.Session()
    session.headers.update({
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/products/ai-video-generator",
    })
    session.get(f"{BASE_URL}/api/auth/csrf", impersonate="chrome", timeout=15)
    return session


def parse_json(resp, label: str) -> dict:
    """Return parsed JSON or raise a readable error instead of a bare decode crash."""
    try:
        return resp.json()
    except ValueError:
        raise RuntimeError(f"{label}: non-JSON response (HTTP {resp.status_code})")


def safe_edit(chat_id: int, message_id: int, text: str) -> None:
    try:
        bot.edit_message_text(text, chat_id, message_id)
    except telebot.apihelper.ApiTelegramException as exc:
        if "message is not modified" not in str(exc):
            log.warning("edit failed: %s", exc)


def prune_pending() -> None:
    now = time.time()
    with pending_lock:
        for cid in [c for c, (_, ts) in pending.items() if now - ts > PENDING_TTL]:
            del pending[cid]


@bot.message_handler(commands=["start"])
def send_welcome(message):
    bot.reply_to(message, "👋 Send me an image, then your prompt.")


@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    file_info = bot.get_file(message.photo[-1].file_id)
    if file_info.file_size and file_info.file_size > MAX_IMAGE_BYTES:
        bot.reply_to(message, "That image is too large. Keep it under 10 MB.")
        return
    image = bot.download_file(file_info.file_path)

    if message.caption:
        start_job(message.chat.id, image, message.caption)
    else:
        with pending_lock:
            pending[message.chat.id] = (image, time.time())
        prune_pending()
        bot.reply_to(message, "📸 Image received. Now send the prompt.")


@bot.message_handler(content_types=["text"])
def handle_text(message):
    chat_id = message.chat.id
    with pending_lock:
        entry = pending.pop(chat_id, None)
    if entry is None:
        bot.reply_to(message, "Send an image first, then type your prompt.")
        return
    start_job(chat_id, entry[0], message.text)


def start_job(chat_id: int, image: bytes, prompt: str) -> None:
    threading.Thread(target=run_job, args=(chat_id, image, prompt), daemon=True).start()


def run_job(chat_id: int, image: bytes, prompt: str) -> None:
    msg = bot.send_message(chat_id, "🔄 Starting...")
    mid = msg.message_id
    try:
        session = new_session()
        task_id = str(uuid.uuid4())

        safe_edit(chat_id, mid, "☁️ Requesting upload slot...")
        r = session.post(
            f"{BASE_URL}/rpc/freeToolUpload/getResumableUploadUrl",
            json={"json": {
                "assetPrefix": "image-to-video", "taskId": task_id,
                "fileName": "source.jpg", "fileType": "image/jpeg",
                "filePrefix": "source", "includeReadUrl": False,
            }},
            impersonate="chrome", timeout=30,
        )
        data = parse_json(r, "upload slot").get("json", {})
        upload_url, file_path = data.get("uploadUrl"), data.get("filePath")
        if r.status_code != 200 or not upload_url or not file_path:
            safe_edit(chat_id, mid, "❌ Could not get an upload slot. Try again later.")
            return

        safe_edit(chat_id, mid, "📤 Uploading image...")
        put = session.put(
            upload_url, data=image, impersonate="chrome", timeout=120,
            headers={
                "Content-Type": "image/jpeg",
                "Content-Range": f"bytes 0-{len(image) - 1}/{len(image)}",
            },
        )
        if put.status_code not in (200, 201):
            safe_edit(chat_id, mid, f"❌ Upload failed (HTTP {put.status_code}).")
            return

        safe_edit(chat_id, mid, "🎬 Starting generation...")
        r = session.post(
            f"{BASE_URL}/api/free-tools/v5/any-to-video",
            json={
                "prompt": prompt, "image_file_path": file_path,
                "aspect_ratio": "9:16", "model": "any-to-video-v5",
                "duration": 5, "client_request_id": task_id,
            },
            impersonate="chrome", timeout=30,
        )
        if r.status_code == 429:
            safe_edit(chat_id, mid, "⛔ Usage limit reached. Try again later.")
            return
        if r.status_code != 200:
            safe_edit(chat_id, mid, f"❌ Could not start the job (HTTP {r.status_code}).")
            return

        start = time.time()
        while True:
            if time.time() - start > MAX_WAIT_SECONDS:
                safe_edit(chat_id, mid, "⌛ Timed out waiting for the render.")
                return

            r = session.get(
                f"{BASE_URL}/api/free-tools/v5/any-to-video/{task_id}/status",
                impersonate="chrome", timeout=15,
            )
            job = parse_json(r, "status")
            status = job.get("status")
            elapsed = int(time.time() - start)
            timer = f"{elapsed // 60}m {elapsed % 60}s"

            if status == "SUCCESS":
                files = job.get("files") or []
                if not files:
                    safe_edit(chat_id, mid, "❌ Render finished but returned no file.")
                    return
                video = session.get(files[0]["url"], impersonate="chrome", timeout=120)
                bot.delete_message(chat_id, mid)
                bot.send_video(
                    chat_id, video.content,
                    caption=f"✅ Done in {timer}\nPrompt: {prompt}",
                )
                return

            if status == "FAILED":
                safe_edit(chat_id, mid, f"❌ Render failed after {timer}.")
                return

            position = job.get("position", "?")
            safe_edit(chat_id, mid, f"⏳ Rendering ({timer})\nQueue position: {position}")
            time.sleep(POLL_INTERVAL)

    except Exception as exc:
        log.exception("job for chat %s failed", chat_id)
        safe_edit(chat_id, mid, "❌ Something went wrong. Try again later.")


if __name__ == "__main__":
    log.info("Magic Hour bot is running")
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
