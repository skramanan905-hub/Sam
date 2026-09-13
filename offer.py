#!/usr/bin/env python3
"""
Super Offer — Telegram Bot + Multi-Account Stage Runner
Single file: main.py
"""

import os
import sys
import json
import time
import base64
import sqlite3
import threading
import traceback
import requests
from datetime import datetime
from flask import Flask, request, jsonify

BOT_TOKEN = os.environ.get("8817040407:AAHxM7D7l5Cc7yuIZvpaeS7guyIzQic9fQI", "").strip()
CHAT_ID   = os.environ.get("1827265590", "").strip()
PORT      = int(os.environ.get("PORT", "10000"))
DB_PATH   = os.environ.get("DB_PATH", "/data/accounts.db")

if not os.path.isdir(os.path.dirname(DB_PATH)):
    DB_PATH = "accounts.db"

BASE = "https://api.offerplay.in"

GAME_SURVIVE_SEC   = 35
GAME_WAIT_AFTER    = 5
AD_WATCH_SEC       = 20
INSTALL_WAIT_SEC   = 30
USAGE_WAIT_SEC     = 125
CLAIM_GAP_SEC      = 3
GEM_FARM_MARGIN    = 5

INSTALL_APPS = {
    2:  {"package": "com.vedantu.app",       "name": "Vedantu"},
    5:  {"package": "com.phonepe.app",       "name": "PhonePe"},
    8:  {"package": "in.swiggy.android",     "name": "Swiggy"},
    12: {"package": "com.flipkart.android",  "name": "Flipkart"},
    15: {"package": "com.myntra.android",    "name": "Myntra"},
    18: {"package": "net.one97.paytm",       "name": "Paytm"},
}

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def log(*args):
    print(f"[{datetime.utcnow():%H:%M:%S}]", *args, flush=True)
def db_init():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT NOT NULL,
            token    TEXT NOT NULL UNIQUE,
            user_id  TEXT,
            added_at TEXT NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS state (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    return conn


DB = db_init()
DB_LOCK = threading.Lock()


def db_add_account(name, token):
    uid = user_id_from_token(token)
    with DB_LOCK:
        c = DB.cursor()
        try:
            c.execute(
                "INSERT INTO accounts (name, token, user_id, added_at) VALUES (?,?,?,?)",
                (name, token, uid, datetime.utcnow().isoformat())
            )
            DB.commit()
            return c.lastrowid
        except sqlite3.IntegrityError:
            return None


def db_list_accounts():
    with DB_LOCK:
        c = DB.cursor()
        c.execute("SELECT id, name, user_id, added_at FROM accounts ORDER BY id")
        return c.fetchall()


def db_get_account(acc_id):
    with DB_LOCK:
        c = DB.cursor()
        c.execute("SELECT id, name, token, user_id FROM accounts WHERE id=?", (acc_id,))
        return c.fetchone()


def db_remove_account(acc_id):
    with DB_LOCK:
        c = DB.cursor()
        c.execute("DELETE FROM accounts WHERE id=?", (acc_id,))
        DB.commit()
        return c.rowcount > 0


def state_set(key, value):
    with DB_LOCK:
        c = DB.cursor()
        c.execute("INSERT OR REPLACE INTO state (key, value) VALUES (?,?)", (key, value))
        DB.commit()


def state_get(key, default=None):
    with DB_LOCK:
        c = DB.cursor()
        c.execute("SELECT value FROM state WHERE key=?", (key,))
        row = c.fetchone()
        return row[0] if row else default


def decode_jwt_payload(token):
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception as e:
        return {"error": str(e)}


def user_id_from_token(token):
    p = decode_jwt_payload(token)
    return p.get("userId")


def token_days_left(token):
    p = decode_jwt_payload(token)
    exp = p.get("exp", 0)
    return (exp - time.time()) / 86400
def tg_send(chat_id, text, reply_markup=None, parse_mode="Markdown"):
    body = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if reply_markup:
        body["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(f"{TG_API}/sendMessage", data=body, timeout=15)
    except Exception as e:
        log("tg_send error:", e)


def tg_edit(chat_id, message_id, text, reply_markup=None, parse_mode="Markdown"):
    body = {"chat_id": chat_id, "message_id": message_id,
            "text": text, "parse_mode": parse_mode}
    if reply_markup:
        body["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(f"{TG_API}/editMessageText", data=body, timeout=15)
    except Exception as e:
        log("tg_edit error:", e)


def tg_answer_cb(cb_id, text=None):
    body = {"callback_query_id": cb_id}
    if text:
        body["text"] = text
    try:
        requests.post(f"{TG_API}/answerCallbackQuery", data=body, timeout=10)
    except Exception:
        pass


def headers_for(token):
    return {
        "accept": "application/json, text/plain, */*",
        "authorization": f"Bearer {token}",
        "x-platform": "android",
        "x-app-version": "81229",
        "x-is-rooted": "false",
        "x-is-emulator": "false",
        "x-device-fingerprint": "dev_248f03ee566cfa70|iQOO|I2301|15",
        "x-device-ua": ("Mozilla/5.0 (Linux; Android 15; I2301 Build/AP3A.240905.015.A2; wv) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
                        "Chrome/152.0.7977.88 Mobile Safari/537.36"),
        "content-type": "application/json",
        "user-agent": "okhttp/4.10.0",
        "accept-encoding": "gzip",
    }


def api_get(token, path, params=None):
    r = requests.get(f"{BASE}{path}", headers=headers_for(token), params=params, timeout=30)
    return r.json()


def api_post(token, path, body=None):
    r = requests.post(f"{BASE}{path}", headers=headers_for(token), json=body or {}, timeout=30)
    return r.json()


def gap(sec, label="waiting", notifier=None):
    if notifier:
        notifier(f"⏳ {sec}s — {label}")
    end = time.time() + sec
    while time.time() < end:
        time.sleep(min(5, max(0.5, end - time.time())))
    if notifier:
        notifier(f"✅ {label}")


def fetch_status(token):
    j = api_get(token, "/api/superoffers/status")
    if not j.get("success"):
        raise RuntimeError(f"status failed: {j}")
    return j["data"]


def parse_iso_ms(iso):
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None
def farm_one_run(token, notifier=None):
    cfg = api_post(token, "/api/ballmaxxing/gem-config", {}).get("data", {}) or {}
    milestones  = cfg.get("milestones", [])
    claimed_idx = cfg.get("ladderClaimedIdx", -1)
    daily_total = cfg.get("dailyEarnedToday", 0)
    daily_cap   = cfg.get("dailyCap", 60)

    if daily_total >= daily_cap:
        if notifier: notifier("⚠️ daily gem cap reached")
        return 0

    next_idx = claimed_idx + 1
    if next_idx >= len(milestones):
        if notifier: notifier(f"⚠️ all rungs claimed this session")
        return 0

    target_secs, target_gems = milestones[next_idx]
    actual_wait = target_secs + GEM_FARM_MARGIN
    if notifier:
        notifier(f"🎯 rung #{next_idx}: survive {target_secs}s → +{target_gems} 💎")

    start = api_post(token, "/api/ballmaxxing/start", {})
    if not start.get("success"):
        if notifier: notifier(f"❌ bm/start: {start}")
        return 0
    s = start["data"]

    gap(actual_wait, "ballmaxxing run", notifier)

    run = api_post(token, "/api/ballmaxxing/run", {
        "sessionId":  s["sessionId"],
        "token":      s["token"],
        "total":      3000,
        "surgeBonus": 0,
        "airBonus":   500,
        "survivalMs": actual_wait * 1000,
        "saves":      25,
        "revives":    0,
        "quit":       False,
    })
    d = run.get("data", {})
    aw = d.get("gemsAwarded", 0)
    if notifier:
        notifier(f"💎 +{aw}  daily={d.get('gemDailyTotal')}/{d.get('gemDailyCap')}")
    return aw


def farm_until(token, target, notifier=None):
    zero_streak = 0
    while True:
        st = fetch_status(token)
        bal = st["currentGemBalance"]
        if bal >= target:
            return bal
        if notifier: notifier(f"farming… balance={bal} need={target}")
        gained = farm_one_run(token, notifier)
        if gained == 0:
            zero_streak += 1
            if zero_streak >= 3:
                return bal
            gap(5, "retry backoff", notifier)
        else:
            zero_streak = 0


def enter_stage(token, notifier=None):
    r = api_post(token, "/api/superoffers/enter", {})
    if not r.get("success"):
        if notifier: notifier(f"❌ enter: {r}")
        return None
    d = r["data"]
    if notifier:
        notifier(f"✅ entered #{d['attempt_id']} cost={d['gems_cost']} install={d['has_app_install_step']}")
    return d["attempt_id"]


def run_game(token, attempt_id, notifier=None):
    gap(GAME_SURVIVE_SEC, "ballmaxxing (in-stage)", notifier)
    api_post(token, "/api/superoffers/game-complete", {
        "attempt_id":  attempt_id,
        "source":      "ballmaxxing",
        "goals":       2500,
        "elapsed_sec": GAME_SURVIVE_SEC,
    })
    gap(GAME_WAIT_AFTER, "score registration", notifier)


def run_ad(token, attempt_id, notifier=None):
    gap(AD_WATCH_SEC, "rewarded ad", notifier)
    api_post(token, "/api/superoffers/ad-complete", {"attempt_id": attempt_id})


def run_install(token, attempt_id, stage_num, notifier=None):
    app = INSTALL_APPS.get(stage_num, {"package": f"com.filler.app{stage_num}",
                                       "name": f"App{stage_num}"})
    gap(INSTALL_WAIT_SEC, f"install {app['name']}", notifier)
    api_post(token, "/api/superoffers/install-detected", {
        "attempt_id":  attempt_id,
        "app_package": app["package"],
        "app_name":    app["name"],
    })
    gap(USAGE_WAIT_SEC, "app usage (≥120s)", notifier)
    api_post(token, "/api/superoffers/verify-usage", {
        "attempt_id":    attempt_id,
        "usage_minutes": 2,
    })


def claim(token, attempt_id, user_id, notifier=None):
    gap(CLAIM_GAP_SEC, "before claim", notifier)
    spend_id = f"SO_{attempt_id}_{user_id}_{int(time.time() * 1000)}"
    r = api_post(token, "/api/superoffers/complete", {
        "attempt_id": attempt_id,
        "spend_id":   spend_id,
    })
    d = r.get("data", {})
    if notifier:
        notifier(f"✅ CLAIM coins={d.get('coins_awarded')} bal={d.get('new_coin_balance')} cd={d.get('cooldown_hours')}h")
    return d


def execute_stage(acc, notifier=None):
    acc_id, name, token, user_id = acc

    def N(msg):
        if notifier:
            notifier(msg)

    st = fetch_status(token)
    ip = st.get("inProgressAttempt")

    if ip is None:
        if not st["canEnter"]:
            cd = parse_iso_ms(st.get("cooldownEndsAt"))
            if cd and cd > time.time():
                wait = int(cd - time.time()) + 2
                N(f"🛏 cooldown {wait}s")
                time.sleep(wait)
            st = fetch_status()
            if not st["canEnter"]:
                N("❌ still cannot enter")
                return False

        if st["currentGemBalance"] < st["gemsCost"]:
            farm_until(token, st["gemsCost"], N)

        attempt_id = enter_stage(token, N)
        if not attempt_id:
            return False
        state = "pending"
    else:
        attempt_id = ip["id"]
        state = ip.get("status", "pending")
        N(f"↩️ resume #{attempt_id} state={state}")

    if state == "pending":
        run_game(token, attempt_id, N)
        state = "game_done"

    if state in ("pending", "game_done"):
        run_ad(token, attempt_id, N)
        state = "ad_watched"

    stage_num = st["attemptNumber"]
    install_flag = bool(next((r["install"] for r in st["ladder"] if r["stage"] == stage_num), False))
    if install_flag and state in ("pending", "game_done", "ad_watched"):
        run_install(token, attempt_id, stage_num, N)

    claim(token, attempt_id, user_id, N)
    return True
RUNNING_JOBS = {}


def is_job_running(acc_id):
    return RUNNING_JOBS.get(acc_id, False)


def run_in_thread(acc_id, fn, *args):
    if is_job_running(acc_id):
        return False
    RUNNING_JOBS[acc_id] = True

    def wrapper():
        try:
            fn(*args)
        except Exception as e:
            log("job error:", e, traceback.format_exc())
        finally:
            RUNNING_JOBS[acc_id] = False

    t = threading.Thread(target=wrapper, daemon=True)
    t.start()
    return True


def kb_main():
    rows = []
    for acc in db_list_accounts():
        acc_id, name, uid, _ = acc
        running = "🟢 " if is_job_running(acc_id) else ""
        rows.append([{"text": f"{running}{name}", "callback_data": f"acc:{acc_id}"}])
    rows.append([{"text": "➕ Add Account", "callback_data": "add"}])
    rows.append([{"text": "🔄 Refresh", "callback_data": "home"}])
    return {"inline_keyboard": rows}


def kb_account(acc_id):
    return {"inline_keyboard": [
        [{"text": "📊 Status",       "callback_data": f"status:{acc_id}"}],
        [{"text": "▶️ Run Next",      "callback_data": f"runnext:{acc_id}"}],
        [{"text": "🏁 Run All",       "callback_data": f"runall:{acc_id}"}],
        [{"text": "💰 Farm Gems",     "callback_data": f"farm:{acc_id}"}],
        [{"text": "🗑 Remove",        "callback_data": f"rm:{acc_id}"}],
        [{"text": "◀️ Back",          "callback_data": "home"}],
    ]}


def kb_confirm_remove(acc_id):
    return {"inline_keyboard": [
        [{"text": "✅ Yes, remove", "callback_data": f"rmyes:{acc_id}"}],
        [{"text": "❌ Cancel",       "callback_data": f"acc:{acc_id}"}],
    ]}


def main_menu_text():
    accs = db_list_accounts()
    lines = ["*Super Offer Bot*", f"Accounts: *{len(accs)}*", ""]
    if not accs:
        lines.append("_No accounts yet. Tap ➕ Add Account._")
    else:
        for acc in accs:
            acc_id, name, uid, _ = acc
            running = " 🟢" if is_job_running(acc_id) else ""
            lines.append(f"• #{acc_id} — *{name}*{running}")
    return "\n".join(lines)


def account_text(acc_id):
    acc = db_get_account(acc_id)
    if not acc:
        return "_Account not found._"
    _, name, token, uid = acc
    days = token_days_left(token)
    try:
        st = fetch_status(token)
        stage = st["attemptNumber"]
        gems  = st["currentGemBalance"]
        can   = st["canEnter"]
        cd    = st.get("cooldownEndsAt") or "—"
        inprog = st.get("inProgressAttempt")
        inprog_txt = f"`{inprog['status']}` (id={inprog['id']})" if inprog else "—"
    except Exception as e:
        stage = gems = "?"
        can   = False
        cd    = f"err: {e}"
        inprog_txt = "—"

    running = "🟢 RUNNING" if is_job_running(acc_id) else "⚪ idle"
    return (
        f"*Account #{acc_id} — {name}*\n"
        f"uid: `{uid}`\n"
        f"token: {days:.1f} days left\n"
        f"status: {running}\n\n"
        f"*Stage:* {stage} / 20\n"
        f"*Gems:* {gems}\n"
        f"*canEnter:* {can}\n"
        f"*cooldown:* {cd}\n"
        f"*inProgress:* {inprog_txt}"
    )
def handle_callback(cb):
    cb_id   = cb["id"]
    chat_id = cb["message"]["chat"]["id"]
    msg_id  = cb["message"]["message_id"]
    data    = cb.get("data", "")

    if data == "home":
        tg_answer_cb(cb_id)
        tg_edit(chat_id, msg_id, main_menu_text(), kb_main())
        return

    if data == "add":
        tg_answer_cb(cb_id)
        state_set(f"await:{chat_id}", "add")
        tg_edit(chat_id, msg_id,
                "Send the token in this format:\n\n`name | bearer_token`\n\n"
                "Send /cancel to abort.",
                {"inline_keyboard": [[{"text":"❌ Cancel","callback_data":"home"}]]})
        return

    if data.startswith("acc:"):
        acc_id = int(data.split(":")[1])
        tg_answer_cb(cb_id)
        tg_edit(chat_id, msg_id, account_text(acc_id), kb_account(acc_id))
        return

    if data.startswith("status:"):
        acc_id = int(data.split(":")[1])
        tg_answer_cb(cb_id, "Refreshing…")
        tg_edit(chat_id, msg_id, account_text(acc_id), kb_account(acc_id))
        return

    if data.startswith("rm:"):
        acc_id = int(data.split(":")[1])
        tg_answer_cb(cb_id)
        tg_edit(chat_id, msg_id, f"Remove account *#{acc_id}*?", kb_confirm_remove(acc_id))
        return

    if data.startswith("rmyes:"):
        acc_id = int(data.split(":")[1])
        ok = db_remove_account(acc_id)
        tg_answer_cb(cb_id, "Removed" if ok else "Not found")
        tg_edit(chat_id, msg_id, main_menu_text(), kb_main())
        return

    if data.startswith("runnext:"):
        acc_id = int(data.split(":")[1])
        tg_answer_cb(cb_id, "Starting…")
        _start_run_next(chat_id, acc_id)
        return

    if data.startswith("runall:"):
        acc_id = int(data.split(":")[1])
        tg_answer_cb(cb_id, "Starting…")
        _start_run_all(chat_id, acc_id)
        return

    if data.startswith("farm:"):
        acc_id = int(data.split(":")[1])
        tg_answer_cb(cb_id, "Farming…")
        _start_farm(chat_id, acc_id)
        return

    tg_answer_cb(cb_id)


def _start_run_next(chat_id, acc_id):
    acc = db_get_account(acc_id)
    if not acc:
        tg_send(chat_id, "Account not found"); return

    def notifier(msg):
        tg_send(chat_id, f"*#{acc_id}* {msg}")

    def job():
        tg_send(chat_id, f"*#{acc_id}* ▶️ run next stage…")
        try:
            ok = execute_stage(acc, notifier)
            tg_send(chat_id, f"*#{acc_id}* {'✅ done' if ok else '❌ failed'}")
        except Exception as e:
            tg_send(chat_id, f"*#{acc_id}* 💥 {e}")

    if not run_in_thread(acc_id, job):
        tg_send(chat_id, f"*#{acc_id}* already running")


def _start_run_all(chat_id, acc_id):
    acc = db_get_account(acc_id)
    if not acc:
        tg_send(chat_id, "Account not found"); return

    def notifier(msg):
        tg_send(chat_id, f"*#{acc_id}* {msg}")

    def job():
        tg_send(chat_id, f"*#{acc_id}* 🏁 running all available stages…")
        while True:
            try:
                st = fetch_status(acc[2])
                if st["attemptNumber"] > 20 or st.get("weekComplete"):
                    tg_send(chat_id, f"*#{acc_id}* 🎉 week complete")
                    return
                ok = execute_stage(acc, notifier)
                if not ok:
                    tg_send(chat_id, f"*#{acc_id}* ❌ stopping"); return
                st = fetch_status(acc[2])
                cd = parse_iso_ms(st.get("cooldownEndsAt"))
                if cd and cd > time.time():
                    wait = int(cd - time.time()) + 2
                    notifier(f"🛏 cooldown {wait}s")
                    time.sleep(wait)
            except Exception as e:
                tg_send(chat_id, f"*#{acc_id}* 💥 {e}"); return

    if not run_in_thread(acc_id, job):
        tg_send(chat_id, f"*#{acc_id}* already running")


def _start_farm(chat_id, acc_id):
    acc = db_get_account(acc_id)
    if not acc:
        tg_send(chat_id, "Account not found"); return

    def notifier(msg):
        tg_send(chat_id, f"*#{acc_id}* {msg}")

    def job():
        tg_send(chat_id, f"*#{acc_id}* 💰 farming gems…")
        try:
            bal = farm_until(acc[2], 999, notifier)
            tg_send(chat_id, f"*#{acc_id}* balance={bal}")
        except Exception as e:
            tg_send(chat_id, f"*#{acc_id}* 💥 {e}")

    if not run_in_thread(acc_id, job):
        tg_send(chat_id, f"*#{acc_id}* already running")


def handle_message(msg):
    chat_id = msg["chat"]["id"]
    text    = (msg.get("text") or "").strip()

    if text == "/cancel":
        state_set(f"await:{chat_id}", "")
        tg_send(chat_id, "Cancelled.", kb_main())
        return

    if state_get(f"await:{chat_id}") == "add":
        if "|" not in text:
            tg_send(chat_id, "Format: `name | bearer_token`"); return
        name, token = [p.strip() for p in text.split("|", 1)]
        if not name or not token:
            tg_send(chat_id, "Both name and token are required."); return
        uid = user_id_from_token(token)
        if not uid:
            tg_send(chat_id, "❌ Token doesn't contain a userId."); return
        new_id = db_add_account(name, token)
        state_set(f"await:{chat_id}", "")
        if new_id is None:
            tg_send(chat_id, "❌ Token already exists.")
        else:
            tg_send(chat_id, f"✅ Added *#{new_id}* — {name}\nuid: `{uid}`", kb_main())
        return

    if text.startswith("/start") or text.startswith("/accounts"):
        tg_send(chat_id, main_menu_text(), kb_main()); return

    if text.startswith("/add"):
        state_set(f"await:{chat_id}", "add")
        tg_send(chat_id, "Send `name | bearer_token` (or /cancel)"); return

    tg_send(chat_id, "Use /start to open menu", kb_main())


def poll_loop():
    offset = 0
    log("Telegram poll loop started")
    while True:
        try:
            r = requests.get(
                f"{TG_API}/getUpdates",
                params={"offset": offset, "timeout": 25,
                        "allowed_updates": json.dumps(["message","callback_query"])},
                timeout=35,
            )
            data = r.json()
            if not data.get("ok"):
                log("getUpdates not ok:", data); time.sleep(3); continue
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                try:
                    if "callback_query" in upd:
                        handle_callback(upd["callback_query"])
                    elif "message" in upd:
                        handle_message(upd["message"])
                except Exception as e:
                    log("update error:", e, traceback.format_exc())
        except requests.exceptions.ReadTimeout:
            continue
        except Exception as e:
            log("poll error:", e); time.sleep(3)


app = Flask(__name__)


@app.route("/")
def root():
    return jsonify({"ok": True, "service": "superoffer-bot",
                    "accounts": len(db_list_accounts()),
                    "time": datetime.utcnow().isoformat() + "Z"})


@app.route("/health")
def health():
    return "ok", 200


@app.route("/run/<int:acc_id>")
def http_run(acc_id):
    acc = db_get_account(acc_id)
    if not acc:
        return jsonify({"error": "account not found"}), 404
    if is_job_running(acc_id):
        return jsonify({"error": "already running"}), 409

    def job():
        try:
            execute_stage(acc, lambda m: log(f"#{acc_id} {m}"))
        except Exception as e:
            log("http_run error:", e)

    run_in_thread(acc_id, job)
    return jsonify({"ok": True, "started": acc_id})


def boot():
    if not BOT_TOKEN:
        log("⚠️  BOT_TOKEN not set.")
    else:
        threading.Thread(target=poll_loop, daemon=True).start()
    log("Boot complete. DB:", DB_PATH)


boot()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
