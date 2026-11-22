#!/usr/bin/env python3
"""
magic_bot.py: Telegram bot for magichour.ai's free image-to-video tool.

Flow (from the HAR log):
  1. POST /rpc/freeToolUpload/getResumableUploadUrl  -> signed GCS upload URL
  2. PUT  <uploadUrl>                                -> image bytes
  3. POST /api/free-tools/v5/any-to-video            -> queue IMAGE_TO_VIDEO job
  4. GET  /api/free-tools/v5/any-to-video/{id}/status -> poll until SUCCESS
  5. GET  <signed output url>                        -> mp4, sent to Telegram

Setup in Termux:
  pkg install python
  pip install "python-telegram-bot==21.*" requests
  python 140.py
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
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
TOKEN_FILE = Path(__file__).with_name("bot_token.txt")
MAX_CHUNK = 3800  # Telegram caps messages at 4096 characters

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
# Token handling
# ---------------------------------------------------------------------------

def get_token(cli_token: str | None) -> str:
    """Use --token, then the env var, then the saved file, else ask once and save it."""
    if cli_token:
        return cli_token.strip()

    env_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if env_token:
        return env_token.strip()

    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text(encoding="utf-8").strip()

    token = getpass.getpass("Paste your Telegram bot token (input hidden): ").strip()
    if ":" not in token:
        sys.exit("That does not look like a bot token. It should contain a colon.")

    TOKEN_FILE.write_text(token + "\n", encoding="utf-8")
    os.chmod(TOKEN_FILE, 0o600)
    print(f"Saved token to {TOKEN_FILE}")
    return token


# ---------------------------------------------------------------------------
# Raw response output: queued, rate-limit safe
# ---------------------------------------------------------------------------

async def send_raw(bot: Bot, chat_id: int, label: str, obj) -> None:
    """Send a raw response to the chat, split into chunks if it is long."""
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
                # Telegram flood control: wait the requested time and retry.
                await asyncio.sleep(float(exc.retry_after) + 1)
            except BadRequest as exc:
                log.warning("could not send raw message: %s", exc)
                break


async def outbox_worker(app: Application) -> None:
    """Drain raw messages one at a time so they never flood Telegram."""
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


def _safe_json(r: requests.Response):
    try:
        return r.json()
    except ValueError:
        return r.text[:2000]


# ---------------------------------------------------------------------------
# magichour.ai client
# ---------------------------------------------------------------------------

class MagicClient:
    """Wrapper around the free-tool endpoints. Raw responses go to emit()."""

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
            pass  # "message is not modified" and similar

    if s.dry_run:
        await set_status(f"Dry run: would render with prompt: {prompt}")
        return

    # Worker threads call these; they hand work to the event loop safely.
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

        # Send the URL as soon as the job succeeds, before downloading.
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

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Telegram bot for magichour.ai free image-to-video.")
    
    # YOUR TOKEN AND USER ID ARE PRE-FILLED HERE
    p.add_argument("--token", default="8890014279:AAGuKNVfg2WJ21DXCS_kBXgVlexjRxXUhL8",
                   help="Telegram bot token")
    p.add_argument("--allow", default="1827265590",
                   help="Comma-separated Telegram user IDs allowed to use the bot (required)")
                   
    p.add_argument("--poll-interval", type=float, default=5.0,
                   help="Seconds between status checks (default 5)")
    p.add_argument("--max-wait", type=float, default=900.0,
                   help="Give up on a job after this many seconds (default 900)")
    p.add_argument("--http-timeout", type=float, default=30.0,
                   help="Timeout per HTTP request in seconds (default 30)")
    p.add_argument("--concurrency", type=int, default=1,
                   help="Jobs allowed to run at once across all users (default 1)")
    p.add_argument("--send-limit-mb", type=float, default=49.0,
                   help="Largest video to upload to Telegram (default 49)")
    p.add_argument("--default-prompt", default="Gentle camera motion",
                   help="Prompt used when none is given")
    p.add_argument("--no-raw", action="store_true",
                   help="Do not send raw responses to Telegram")
    p.add_argument("--dry-run", action="store_true",
                   help="Do not call magichour.ai; only test the Telegram side")
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    a = parse_args(argv)
    logging.basicConfig(
        level=a.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    token = get_token(a.token)

    try:
        allowed = frozenset(int(x) for x in a.allow.split(",") if x.strip())
    except ValueError:
        sys.exit("--allow must be comma-separated numeric Telegram user IDs")
    if not allowed:
        sys.exit("Refusing to start with no allowed users: pass --allow <your_user_id>")

    s = Settings(
        token=token,
        allowed=allowed,
        poll_interval=a.poll_interval,
        max_wait=a.max_wait,
        http_timeout=a.http_timeout,
        concurrency=max(1, a.concurrency),
        send_limit_mb=a.send_limit_mb,
        default_prompt=a.default_prompt,
        dry_run=a.dry_run,
        raw_to_chat=not a.no_raw,
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
