#!/usr/bin/env python3
"""
magic_bot.py: Telegram bot for magichour.ai's free image-to-video tool.
Optimized for Render.com (includes health-check web server).
"""
from __future__ import annotations

import argparse
import asyncio
import html
import io
import json
import logging
import os
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import requests
from aiohttp import web
from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
    Update,
)
from telegram.error import BadRequest, RetryAfter
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

BASE_URL = "https://magichour.ai"
USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 15; Mobile) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/157.0.0.0 Mobile Safari/537.36"
)
FAILED_STATES = {"FAILED", "ERROR", "CANCELED", "CANCELLED"}
MAX_CHUNK = 3800

log = logging.getLogger("magic_bot")

MENU_TEXT = (
    "Image to video\n\n"
    "Send a photo with a caption as the prompt, or set a prompt first "
    "and then send the photo."
)
HELP_TEXT = (
    "Commands:\n"
    "/start or /help: this menu\n"
    "/prompt <text>: set a default prompt\n\n"
    "Send a photo: its caption is used as the prompt. "
    "Without a caption, your saved prompt or the default is used."
)

@dataclass(frozen=True)
class Settings:
    token: str
    allowed: frozenset[int]
    poll_interval: float
    max_wait: float
    http_timeout: float
    concurrency: int
    send_limit_mb: float
    default_prompt: str
    dry_run: bool
    raw_to_chat: bool

# ---------------------------------------------------------------------------
# Render Health Check Server
# ---------------------------------------------------------------------------

async def handle_ping(request):
    return web.Response(text="Bot is alive!")

async def start_web_server():
    """Starts a dummy web server on the port Render provides."""
    app = web.Application()
    app.router.add_get("/", handle_ping)
    
    # Render assigns a PORT env variable. Default to 8080 if not found.
    port = int(os.environ.get("PORT", 8080))
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info(f"Health check server running on port {port}")

# ---------------------------------------------------------------------------
# Raw response output: queued, rate-limit safe
# ---------------------------------------------------------------------------

async def send_raw(bot: Bot, chat_id: int, label: str, obj) -> None:
    body = obj if isinstance(obj, str) else json.dumps(
        obj, indent=2, ensure_ascii=False, default=str
    )
    chunks = [body[i:i + MAX_CHUNK] for i in range(0, len(body), MAX_CHUNK)] or [""]
    for n, chunk in enumerate(chunks, 1):
        tag = f"{label} ({n}/{len(chunks)})" if len(chunks) > 1 else label
        text = f"<b>{html.escape(tag)}</b>\n<pre>{html.escape(chunk)}</pre>"
        while True:
            try:
                await bot.send_message(chat_id, text, parse_mode="HTML")
                break
            except RetryAfter as exc:
                await asyncio.sleep(float(exc.retry_after) + 1)
            except BadRequest as exc:
                log.warning("could not send raw message: %s", exc)
                break

async def outbox_worker(app: Application) -> None:
    queue: asyncio.Queue = app.bot_data["outbox"]
    while True:
        chat_id, label, obj = await queue.get()
        try:
            await send_raw(app.bot, chat_id, label, obj)
        except Exception:
            log.exception("outbox send failed")
        finally:
            queue.task_done()

async def post_init(app: Application) -> None:
    app.bot_data["outbox"] = asyncio.Queue()
    app.create_task(outbox_worker(app))
    # Start the Render web server alongside the bot
    app.create_task(start_web_server())

def _safe_json(r: requests.Response):
    try:
        return r.json()
    except ValueError:
        return r.text[:2000]

# ---------------------------------------------------------------------------
# magichour.ai client
# ---------------------------------------------------------------------------

class MagicClient:
    def __init__(self, s: Settings):
        self.s = s
        self.http = requests.Session()
        self.http.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Origin": BASE_URL,
            "Referer": f"{BASE_URL}/products/ai-video-generator",
        })

    def upload_image(self, data: bytes, filename: str, task_id: str, emit) -> str:
        r = self.http.post(
            f"{BASE_URL}/rpc/freeToolUpload/getResumableUploadUrl",
            json={"json": {
                "assetPrefix": "image-to-video",
                "taskId": task_id,
                "fileName": filename,
                "fileType": "image/jpeg",
                "filePrefix": "source",
                "includeReadUrl": False,
            }},
            timeout=self.s.http_timeout,
        )
        emit("1. UPLOAD URL RESPONSE", {"http": r.status_code, "body": _safe_json(r)})
        r.raise_for_status()
        info = r.json()["json"]
        if info.get("status") != "success":
            raise RuntimeError(f"upload URL refused: {info}")

        put = requests.put(
            info["uploadUrl"],
            data=data,
            headers={"Content-Type": "image/jpeg"},
            timeout=120,
        )
        emit("2. GCS PUT RESPONSE", {"http": put.status_code, "headers": dict(put.headers)})
        put.raise_for_status()
        return info["filePath"]

    def start_job(self, image_key: str, prompt: str, task_id: str, emit) -> dict:
        r = self.http.post(
            f"{BASE_URL}/api/free-tools/v5/any-to-video",
            json={
                "mode": "IMAGE_TO_VIDEO",
                "image_key": image_key,
                "prompt": prompt,
                "task_id": task_id,
            },
            timeout=self.s.http_timeout,
        )
        body = _safe_json(r)
        emit("3. QUEUE RESPONSE", {"http": r.status_code, "body": body})
        r.raise_for_status()
        return body

    def wait_for_result(self, task_id: str, emit, progress) -> str:
        url = f"{BASE_URL}/api/free-tools/v5/any-to-video/{task_id}/status"
        started = time.monotonic()
        deadline = started + self.s.max_wait
        poll = 0
        while True:
            poll += 1
            r = self.http.get(url, timeout=self.s.http_timeout)
            j = _safe_json(r)
            elapsed = int(time.monotonic() - started)
            emit(f"4. STATUS POLL #{poll} (HTTP {r.status_code}, {elapsed}s)", j)
            r.raise_for_status()

            status = j.get("status", "UNKNOWN") if isinstance(j, dict) else "UNKNOWN"
            remaining = j.get("remaining") if isinstance(j, dict) else None
            progress(status, elapsed, remaining)

            if status == "SUCCESS":
                urls = j.get("urls") or []
                if not urls:
                    raise RuntimeError("job reported SUCCESS with no output URL")
                return urls[0]
            if status in FAILED_STATES:
                raise RuntimeError(f"job ended as {status}")
            if time.monotonic() > deadline:
                raise TimeoutError(f"no result after {self.s.max_wait:.0f}s (last status: {status})")

            retry_after = 0.0
            if isinstance(j, dict) and j.get("retryAfter"):
                retry_after = float(j["retryAfter"])
            time.sleep(max(self.s.poll_interval, retry_after))

    def download(self, url: str, emit) -> bytes:
        r = requests.get(url, timeout=300)
        emit("5. DOWNLOAD RESPONSE", {
            "http": r.status_code,
            "content_type": r.headers.get("Content-Type"),
            "bytes": len(r.content),
        })
        r.raise_for_status()
        return r.content

# ---------------------------------------------------------------------------
# Telegram handlers
# ---------------------------------------------------------------------------

def settings_of(context: ContextTypes.DEFAULT_TYPE) -> Settings:
    return context.bot_data["settings"]

def is_allowed(update: Update, s: Settings) -> bool:
    user = update.effective_user
    return bool(user and user.id in s.allowed)

async def deny(update: Update) -> None:
    if update.effective_message:
        await update.effective_message.reply_text("Not authorized.")

def menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Set prompt", callback_data="prompt")],
        [
            InlineKeyboardButton("Status", callback_data="status"),
            InlineKeyboardButton("Help", callback_data="help"),
        ],
    ])

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update, settings_of(context)):
        return await deny(update)
    await update.message.reply_text(MENU_TEXT, reply_markup=menu_markup())

async def cmd_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update, settings_of(context)):
        return await deny(update)
    text = " ".join(context.args or []).strip()
    if text:
        context.user_data["prompt"] = text
        await update.message.reply_text(f"Prompt saved: {text}")
    else:
        context.user_data["awaiting_prompt"] = True
        await update.message.reply_text("Send the prompt text now.")

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    s = settings_of(context)
    if not is_allowed(update, s):
        return await q.answer("Not authorized", show_alert=True)
    await q.answer()

    if q.data == "prompt":
        context.user_data["awaiting_prompt"] = True
        await q.message.reply_text("Send the prompt text now.")
    elif q.data == "status":
        current = context.user_data.get("prompt") or f"(none, default: {s.default_prompt})"
        running = context.bot_data.get("running", 0)
        await q.message.reply_text(f"Prompt: {current}\nJobs running: {running}")
    elif q.data == "help":
        await q.message.reply_text(HELP_TEXT, reply_markup=menu_markup())

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update, settings_of(context)):
        return await deny(update)
    if context.user_data.pop("awaiting_prompt", False):
        text = update.message.text.strip()
        context.user_data["prompt"] = text
        await update.message.reply_text(f"Prompt saved: {text}")
    else:
        await update.message.reply_text(MENU_TEXT, reply_markup=menu_markup())

async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    s = settings_of(context)
    if not is_allowed(update, s):
        return await deny(update)

    running = context.bot_data.get("running", 0)
    if running >= s.concurrency:
        await update.message.reply_text("A job is already running. Try again when it finishes.")
        return

    caption = (update.message.caption or "").strip()
    prompt = caption or context.user_data.get("prompt") or s.default_prompt

    tg_file = await update.message.photo[-1].get_file()
    data = bytes(await tg_file.download_as_bytearray())

    context.bot_data["running"] = running + 1
    try:
        await run_job(update, context, data, prompt)
    finally:
        context.bot_data["running"] -= 1

async def run_job(update: Update, context: ContextTypes.DEFAULT_TYPE,
                  data: bytes, prompt: str) -> None:
    s = settings_of(context)
    client: MagicClient = context.bot_data["client"]
    outbox: asyncio.Queue = context.bot_data["outbox"]
    chat = update.effective_chat
    loop = asyncio.get_running_loop()

    status_msg = await update.message.reply_text("Uploading image...")

    async def set_status(text: str) -> None:
        try:
            await status_msg.edit_text(text)
        except BadRequest:
            pass

    if s.dry_run:
        await set_status(f"Dry run: would render with prompt: {prompt}")
        return

    def emit(label: str, obj) -> None:
        if s.raw_to_chat:
            loop.call_soon_threadsafe(outbox.put_nowait, (chat.id, label, obj))

    def progress(status: str, elapsed: int, remaining) -> None:
        text = f"Status: {status} | {elapsed}s elapsed"
        if remaining is not None:
            text += f" | free jobs left: {remaining}"
        asyncio.run_coroutine_threadsafe(set_status(text), loop)

    task_id = str(uuid.uuid4())
    if s.raw_to_chat:
        outbox.put_nowait((chat.id, "JOB START", {
            "task_id": task_id,
            "prompt": prompt,
            "mode": "IMAGE_TO_VIDEO",
        }))

    try:
        await set_status("Uploading image...")
        image_key = await asyncio.to_thread(
            client.upload_image, data, "photo.jpg", task_id, emit
        )

        await set_status("Queuing job...")
        await asyncio.to_thread(client.start_job, image_key, prompt, task_id, emit)

        await set_status("Waiting in queue...")
        video_url = await asyncio.to_thread(
            client.wait_for_result, task_id, emit, progress
        )

        await chat.send_message(f"Video ready. Link (expires in about an hour):\n{video_url}")

        await set_status("Downloading result...")
        video = await asyncio.to_thread(client.download, video_url, emit)

        size_mb = len(video) / 1_000_000
        caption = f"Done. Prompt: {prompt}"[:1024]
        if size_mb <= s.send_limit_mb:
            await chat.send_video(
                video=InputFile(io.BytesIO(video), filename="output.mp4"),
                caption=caption,
                supports_streaming=True,
            )
        else:
            await chat.send_message(
                f"Video is {size_mb:.1f} MB, over Telegram's limit, so only the link is above."
            )
        await set_status("Finished.")
    except Exception as exc:
        log.exception("job %s failed", task_id)
        if s.raw_to_chat:
            outbox.put_nowait((chat.id, "ERROR", {"task_id": task_id, "error": repr(exc)}))
        await set_status(f"Failed: {exc}")

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # YOUR TOKEN AND ID ARE HARDCODED HERE
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "8890014279:AAGuKNVfg2WJ21DXCS_kBXgVlexjRxXUhL8")
    allow_str = os.environ.get("ALLOWED_USERS", "1827265590")

    if not token:
        sys.exit("Missing TELEGRAM_BOT_TOKEN environment variable.")
    
    try:
        allowed = frozenset(int(x) for x in allow_str.split(",") if x.strip())
    except ValueError:
        sys.exit("ALLOWED_USERS must be comma-separated numeric Telegram user IDs")
    if not allowed:
        sys.exit("Refusing to start with no allowed users: set ALLOWED_USERS environment variable.")

    s = Settings(
        token=token,
        allowed=allowed,
        poll_interval=float(os.environ.get("POLL_INTERVAL", 5.0)),
        max_wait=float(os.environ.get("MAX_WAIT", 900.0)),
        http_timeout=float(os.environ.get("HTTP_TIMEOUT", 30.0)),
        concurrency=int(os.environ.get("CONCURRENCY", 1)),
        send_limit_mb=float(os.environ.get("SEND_LIMIT_MB", 49.0)),
        default_prompt=os.environ.get("DEFAULT_PROMPT", "Gentle camera motion"),
        dry_run=os.environ.get("DRY_RUN", "false").lower() == "true",
        raw_to_chat=os.environ.get("NO_RAW", "false").lower() != "true",
    )

    app = (
        Application.builder()
        .token(s.token)
        .post_init(post_init)
        .build()
    )
    app.bot_data.update(settings=s, client=MagicClient(s), running=0)

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("prompt", cmd_prompt))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    log.info("starting bot; allowed users=%s dry_run=%s", sorted(allowed), s.dry_run)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
