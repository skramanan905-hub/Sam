import os, json, time, sqlite3, threading, html
import traceback, requests, urllib3
from datetime import datetime
from flask import Flask, jsonify

urllib3.disable_warnings()

# ============ CONFIG ============
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8890014279:AAGuKNVfg2WJ21DXCS_kBXgVlexjRxXUhL8")
CHAT_ID   = os.environ.get("CHAT_ID",   "1827265590")

PORT    = int(os.environ.get("PORT", "10000"))
DB_PATH = os.environ.get("DB_PATH", "/data/accounts.db")
if not os.path.isdir(os.path.dirname(DB_PATH)):
    DB_PATH = "accounts.db"
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

VERSION = "1.0.19"
START_TIME = time.time()

GEM_URL   = "https://us-central1-cash-bro-8c96e.cloudfunctions.net/claimGems"
SUPER_URL = "https://us-central1-cash-bro-8c96e.cloudfunctions.net/claimSuperOffer"
GEM_VALUE   = "10"
GEM_CLAIMS  = 20
SUPER_VALUE = "200"
GEM_DELAY   = 2

INSTANCE_ID = ("c83aRHv6QD6dgvLIVax39r:APA91bEpVaezbqZEx5L-qi8LgyiVQ8pD_s8c1iFcuYCLH0CXTvVeimRT3owoNKIEvfB2vAw1yHsQBdrFnExDU-q6ksGxKzFqr_lRdQhaJHTCx9XM7zYbdGY")

RE_BASE    = "https://app.rewardbro.in"
RE_API_KEY = "rb_live_9f3c7a21d8b64e5ab4c2f1e98d6a73c5f0b"
RE_DELAY   = 15

# Stop triggers: if any of these words appear in the API response, stop.
STOP_WORDS = ("daily limit", "limit reached", "limit exceed",
              "no more offer", "no offers", "completed all")


def log(*a):
    print(f"[{datetime.utcnow():%H:%M:%S}]", *a, flush=True)


def esc(s):
    return html.escape(str(s), quote=False)


def _to_int(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


# ============================================================
# DB
# ============================================================
def db_init():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    x = c.cursor()
    x.execute("""CREATE TABLE IF NOT EXISTS acc(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, bearer TEXT, appcheck TEXT, uid TEXT, at TEXT)""")
    x.execute("""CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT)""")
    c.commit()
    return c

DB = db_init()
LK = threading.Lock()


def db_add(name, bearer, appcheck, uid):
    with LK:
        x = DB.cursor()
        x.execute("INSERT INTO acc(name,bearer,appcheck,uid,at) VALUES(?,?,?,?,?)",
                  (name, bearer, appcheck, uid, datetime.utcnow().isoformat()))
        DB.commit()
        return x.lastrowid


def db_list():
    with LK:
        x = DB.cursor()
        x.execute("SELECT id,name,uid FROM acc ORDER BY id")
        return x.fetchall()


def db_get(i):
    with LK:
        x = DB.cursor()
        x.execute("SELECT id,name,bearer,appcheck,uid FROM acc WHERE id=?", (i,))
        return x.fetchone()


def db_del(i):
    with LK:
        x = DB.cursor()
        x.execute("DELETE FROM acc WHERE id=?", (i,))
        DB.commit()
        return x.rowcount > 0


def kv_set(k, v):
    with LK:
        x = DB.cursor()
        x.execute("INSERT OR REPLACE INTO kv VALUES(?,?)", (k, v))
        DB.commit()


def kv_get(k, d=None):
    with LK:
        x = DB.cursor()
        x.execute("SELECT v FROM kv WHERE k=?", (k,))
        r = x.fetchone()
        return r[0] if r else d


# ============================================================
# TG
# ============================================================
def tg_send(cid, t, kb=None):
    d = {"chat_id": cid, "text": t, "parse_mode": "HTML",
         "disable_web_page_preview": True}
    if kb: d["reply_markup"] = json.dumps(kb)
    try:
        r = requests.post(f"{TG_API}/sendMessage", data=d, timeout=15)
        if r.status_code != 200:
            log("tg_send", r.status_code, r.text[:200])
    except Exception as e:
        log("tg_send", e)


def tg_edit(cid, mid, t, kb=None):
    d = {"chat_id": cid, "message_id": mid,
         "text": t, "parse_mode": "HTML",
         "disable_web_page_preview": True}
    if kb: d["reply_markup"] = json.dumps(kb)
    try:
        r = requests.post(f"{TG_API}/editMessageText", data=d, timeout=15)
        if r.status_code != 200 and "not modified" not in r.text:
            log("tg_edit", r.status_code, r.text[:200])
    except Exception as e:
        log("tg_edit", e)


def tg_ans(cbid, t=None):
    d = {"callback_query_id": cbid}
    if t: d["text"] = t
    try:
        requests.post(f"{TG_API}/answerCallbackQuery", data=d, timeout=10)
    except Exception:
        pass


# ============================================================
# CASH BRO API
# ============================================================
def gem_hdr(bearer, appcheck):
    return {
        "host": "us-central1-cash-bro-8c96e.cloudfunctions.net",
        "authorization": f"Bearer {bearer}",
        "x-firebase-appcheck": appcheck,
        "content-type": "application/json; charset=utf-8",
        "user-agent": "okhttp/5.2.1",
    }


def super_hdr(bearer, appcheck):
    h = gem_hdr(bearer, appcheck)
    h["firebase-instance-id-token"] = INSTANCE_ID
    return h


def gem_payload():
    return {"data": {"gems": {
        "@type": "type.googleapis.com/google.protobuf.Int64Value",
        "value": GEM_VALUE}, "isInstall": False}}


def super_payload():
    return {"data": {
        "gemsRequired": {"@type": "type.googleapis.com/google.protobuf.Int64Value",
                         "value": SUPER_VALUE},
        "coins":        {"@type": "type.googleapis.com/google.protobuf.Int64Value",
                         "value": SUPER_VALUE}}}


def run_gems(acc, N):
    _, name, bearer, appcheck, uid = acc
    N(f"💎 claiming {GEM_VALUE} gems × {GEM_CLAIMS}")
    ok = 0
    for i in range(1, GEM_CLAIMS + 1):
        try:
            r = requests.post(GEM_URL, headers=gem_hdr(bearer, appcheck),
                              json=gem_payload(), verify=False, timeout=30)
            if r.status_code == 401:
                N("❌ token expired"); return 0
            if r.status_code == 403:
                N("❌ appcheck rejected"); return 0
            if r.status_code == 200:
                ok += 1
                N(f"[{i}/{GEM_CLAIMS}] ✅")
            else:
                N(f"[{i}/{GEM_CLAIMS}] {r.status_code} {esc(r.text[:80])}")
        except Exception as e:
            N(f"[{i}] 🚨 {esc(e)}")
        if i < GEM_CLAIMS:
            time.sleep(GEM_DELAY)
    N(f"✅ gems {ok}/{GEM_CLAIMS}")
    return ok


def run_super(acc, N):
    _, name, bearer, appcheck, uid = acc
    N(f"⚡ super offer ({SUPER_VALUE})")
    try:
        r = requests.post(SUPER_URL, headers=super_hdr(bearer, appcheck),
                          json=super_payload(), verify=False, timeout=30)
        N(f"super → {r.status_code} | {esc(r.text[:200])}")
    except Exception as e:
        N(f"🚨 super {esc(e)}")


def run_full(acc, N):
    N("🚀 full run")
    run_gems(acc, N)
    time.sleep(GEM_DELAY)
    run_super(acc, N)
    N("🎯 done")


STOPS = set()


def re_hdr():
    return {
        "user-agent": "Dart/3.11 (dart:io)",
        "content-type": "application/json",
        "x-api-key": RE_API_KEY,
        "accept-encoding": "gzip",
        "host": "app.rewardbro.in",
    }


def _is_stop_response(data, raw_text):
    """Return (True, reason) if server says limit reached / no more offers."""
    # 1) check every string field of the json body
    try:
        flat = json.dumps(data).lower()
    except Exception:
        flat = (raw_text or "").lower()
    for w in STOP_WORDS:
        if w in flat:
            return True, w
    return False, ""


def re_loop(acc, N):
    aid = acc[0]
    uid = acc[4]
    N(f"📖 Read &amp; Earn ({RE_DELAY}s interval)")
    count = 0

    while aid not in STOPS:
        count += 1
        try:
            body = json.dumps({"appName": "rewardbro", "userId": uid})
            r = requests.request("GET", f"{RE_BASE}/get-read-earn-url",
                                 headers=re_hdr(), data=body,
                                 verify=False, timeout=30)

            if r.status_code != 200:
                N(f"[{count}] ❌ fetch {r.status_code}")
                time.sleep(RE_DELAY)
                continue

            # ---- parse json safely ----
            try:
                data = r.json()
            except Exception:
                data = {}

            # ---- STOP if server says limit reached ----
            stopped, why = _is_stop_response(data, r.text)
            if stopped:
                N(f"🏁 server says '{esc(why)}' — stopping reads")
                return

            if not data.get("success"):
                N(f"[{count}] ❌ {esc(data.get('message'))}")
                time.sleep(RE_DELAY)
                continue

            oid   = data.get("offerId")
            coins = data.get("coins")
            lim   = data.get("limits")
            done  = data.get("completedCount")

            lim_i  = _to_int(lim)
            done_i = _to_int(done)

            N(f"[{count}] 📥 offer={esc(oid)} coins={esc(coins)} {done}/{lim}")

            # ---- STOP if counter shows limit reached ----
            if lim_i is not None and done_i is not None and done_i >= lim_i:
                N(f"🏁 limit reached ({done_i}/{lim_i}) — stopping reads")
                return

            # ---- STOP if no offer returned ----
            if not oid:
                N("🏁 no offer returned — stopping reads")
                return

            # wait before postback
            for _ in range(RE_DELAY):
                if aid in STOPS: return
                time.sleep(1)

            pb = requests.get(f"{RE_BASE}/read-earn-postback",
                              headers=re_hdr(),
                              params={"appName": "rewardbro",
                                      "userId": uid, "offerId": oid},
                              verify=False, timeout=30)
            N(f"[{count}] 📤 {pb.status_code} {esc(pb.text[:120])}")

        except Exception as e:
            N(f"[{count}] 🚨 {esc(e)}")

        for _ in range(RE_DELAY):
            if aid in STOPS: return
            time.sleep(1)

    N("🛑 stopped")


# ============================================================
# JOBS
# ============================================================
JOBS = {}


def running(i):
    return JOBS.get(i, False)


def spawn(i, fn, *a):
    if running(i): return False
    JOBS[i] = True
    STOPS.discard(i)

    def w():
        try:
            fn(*a)
        except Exception as e:
            log("job", e, traceback.format_exc())
        finally:
            JOBS[i] = False
            STOPS.discard(i)
    threading.Thread(target=w, daemon=True).start()
    return True


# ============================================================
# KEYBOARDS / TEXTS
# ============================================================
def kb_main():
    rows = []
    for i, n, u in db_list():
        pre = "🟢 " if running(i) else ""
        rows.append([{"text": f"{pre}#{i} {n}",
                      "callback_data": f"a:{i}"}])
    rows.append([{"text": "➕ Add Account", "callback_data": "add"}])
    rows.append([{"text": "🔄 Refresh",     "callback_data": "home"}])
    return {"inline_keyboard": rows}


def kb_acc(i):
    rows = []
    if running(i):
        rows.append([{"text": "⏹ Stop", "callback_data": f"st:{i}"}])
    else:
        rows.append([{"text": "🚀 Run Full",     "callback_data": f"cf:{i}"}])
        rows.append([{"text": "💎 Gems Only",    "callback_data": f"cg:{i}"}])
        rows.append([{"text": "⚡ Super Only",   "callback_data": f"cs:{i}"}])
        rows.append([{"text": "📖 Read & Earn",  "callback_data": f"rs:{i}"}])
    rows.append([{"text": "🗑 Remove", "callback_data": f"x:{i}"}])
    rows.append([{"text": "◀️ Back",  "callback_data": "home"}])
    return {"inline_keyboard": rows}


def kb_rm(i):
    return {"inline_keyboard": [
        [{"text": "✅ Yes", "callback_data": f"y:{i}"}],
        [{"text": "❌ No",  "callback_data": f"a:{i}"}],
    ]}


def menu_text():
    accs = db_list()
    L = [f"<b>Reward Bro Bot v{VERSION}</b>",
         f"Accounts: <b>{len(accs)}</b>", ""]
    if not accs:
        L.append("<i>No accounts. Tap ➕ Add.</i>")
    else:
        for i, n, u in accs:
            pre = "🟢" if running(i) else "⚪"
            L.append(f"{pre} <b>#{i}</b> {esc(n)}")
    return "\n".join(L)


def acc_text(i):
    a = db_get(i)
    if not a: return "<i>not found</i>"
    _, name, bearer, appcheck, uid = a
    r  = "🟢 running" if running(i) else "⚪ idle"
    tok = (bearer[:18] + "…")   if bearer   else "—"
    ck  = (appcheck[:18] + "…") if appcheck else "—"
    return (f"<b>Reward Bro #{i} — {esc(name)}</b>\n"
            f"status: {r}\n\n"
            f"userId: <code>{esc(uid)}</code>\n"
            f"bearer: <code>{esc(tok)}</code>\n"
            f"appcheck: <code>{esc(ck)}</code>")


# ============================================================
# ADD FLOW
# ============================================================
def start_add(chat):
    kv_set(f"aw:{chat}", "add")
    kv_set(f"tmp:{chat}:bearer", "")
    kv_set(f"tmp:{chat}:appcheck", "")
    tg_send(chat,
        "➕ <b>Add Account — Step 1 of 3</b>\n\n"
        "Send <b>bearer token</b>:\n"
        "<i>(starts with <code>eyJ...</code>)</i>\n\n"
        "/cancel to abort",
        {"inline_keyboard":
            [[{"text": "❌ Cancel", "callback_data": "home"}]]})


def cancel_add(chat):
    kv_set(f"aw:{chat}", "")
    kv_set(f"tmp:{chat}:bearer", "")
    kv_set(f"tmp:{chat}:appcheck", "")


def handle_add_step(chat, t):
    bearer   = kv_get(f"tmp:{chat}:bearer", "")
    appcheck = kv_get(f"tmp:{chat}:appcheck", "")

    if not bearer:
        if not t.startswith("eyJ"):
            tg_send(chat, "❌ Must start with <code>eyJ...</code>\nTry again:")
            return True
        kv_set(f"tmp:{chat}:bearer", t.replace("Bearer ", ""))
        tg_send(chat,
            "✅ Bearer saved\n\n"
            "➕ <b>Step 2 of 3</b>\n\n"
            "Send <b>appcheck</b> token:\n"
            "<i>(from <code>x-firebase-appcheck</code> header)</i>")
        return True

    if not appcheck:
        if not t.startswith("eyJ"):
            tg_send(chat, "❌ Must start with <code>eyJ...</code>\nTry again:")
            return True
        kv_set(f"tmp:{chat}:appcheck", t)
        tg_send(chat,
            "✅ AppCheck saved\n\n"
            "➕ <b>Step 3 of 3</b>\n\n"
            "Send <b>userId</b>:\n"
            "<i>(numbers or letters, no spaces)</i>")
        return True

    uid = t.strip()
    if not uid or " " in uid or len(uid) > 100:
        tg_send(chat, "❌ Invalid userId.\nSend again:")
        return True

    n = len(db_list()) + 1
    name = f"RB{n}"
    new = db_add(name, bearer, appcheck, uid)
    cancel_add(chat)
    tg_send(chat,
        f"✅ <b>{esc(name)}</b> added (id #{new})\n\n"
        f"userId: <code>{esc(uid)}</code>\n"
        f"bearer: <code>{esc(bearer[:18])}…</code>\n"
        f"appcheck: <code>{esc(appcheck[:18])}…</code>",
        kb_main())
    return False


# ============================================================
# CALLBACKS
# ============================================================
def cb(c):
    cid  = c["id"]
    chat = c["message"]["chat"]["id"]
    mid  = c["message"]["message_id"]
    d    = c.get("data", "")

    if d == "home":
        cancel_add(chat)
        tg_ans(cid)
        tg_edit(chat, mid, menu_text(), kb_main())

    elif d == "add":
        tg_ans(cid)
        start_add(chat)

    elif d.startswith("a:"):
        i = int(d.split(":")[1]); tg_ans(cid)
        tg_edit(chat, mid, acc_text(i), kb_acc(i))

    elif d.startswith("x:"):
        i = int(d.split(":")[1]); tg_ans(cid)
        tg_edit(chat, mid, f"Remove <b>#{i}</b>?", kb_rm(i))

    elif d.startswith("y:"):
        i = int(d.split(":")[1])
        if running(i):
            STOPS.add(i)
            time.sleep(0.3)
        ok = db_del(i)
        tg_ans(cid, "removed" if ok else "nope")
        tg_edit(chat, mid, menu_text(), kb_main())

    elif d.startswith("cf:"):
        i = int(d.split(":")[1]); tg_ans(cid, "…")
        a = db_get(i)
        if a:
            def N(m, _i=i): tg_send(chat, f"<b>#{_i}</b> {m}")
            if spawn(i, run_full, a, N):
                tg_send(chat, f"<b>#{i}</b> 🚀 full run", kb_acc(i))
            else:
                tg_send(chat, f"<b>#{i}</b> already running")

    elif d.startswith("cg:"):
        i = int(d.split(":")[1]); tg_ans(cid, "…")
        a = db_get(i)
        if a:
            def N(m, _i=i): tg_send(chat, f"<b>#{_i}</b> {m}")
            if spawn(i, run_gems, a, N):
                tg_send(chat, f"<b>#{i}</b> 💎 gems", kb_acc(i))
            else:
                tg_send(chat, f"<b>#{i}</b> already running")

    elif d.startswith("cs:"):
        i = int(d.split(":")[1]); tg_ans(cid, "…")
        a = db_get(i)
        if a:
            def N(m, _i=i): tg_send(chat, f"<b>#{_i}</b> {m}")
            if spawn(i, run_super, a, N):
                tg_send(chat, f"<b>#{i}</b> ⚡ super", kb_acc(i))
            else:
                tg_send(chat, f"<b>#{i}</b> already running")

    elif d.startswith("rs:"):
        i = int(d.split(":")[1]); tg_ans(cid, "…")
        a = db_get(i)
        if a:
            def N(m, _i=i): tg_send(chat, f"<b>#{_i}</b> {m}")
            if spawn(i, re_loop, a, N):
                tg_send(chat, f"<b>#{i}</b> 📖 read&amp;earn", kb_acc(i))
            else:
                tg_send(chat, f"<b>#{i}</b> already running")

    elif d.startswith("st:"):
        i = int(d.split(":")[1]); tg_ans(cid, "stopping…")
        if running(i):
            STOPS.add(i)
            tg_send(chat, f"<b>#{i}</b> ⏹ stop", kb_acc(i))
        else:
            tg_send(chat, f"<b>#{i}</b> not running", kb_acc(i))

    else:
        tg_ans(cid)


# ============================================================
# MESSAGES
# ============================================================
def msg(m):
    chat = m["chat"]["id"]
    t = (m.get("text") or "").strip()

    if t == "/cancel":
        cancel_add(chat)
        tg_send(chat, "Cancelled", kb_main())
        return

    if kv_get(f"aw:{chat}") == "add":
        if t.startswith("/"):
            tg_send(chat,
                "⚠️ You're in add-flow. Send the value or /cancel to abort.")
            return
        handle_add_step(chat, t)
        return

    if t.startswith("/start") or t.startswith("/menu") or t == "/help":
        tg_send(chat, menu_text(), kb_main()); return
    if t.startswith("/add"):
        start_add(chat); return

    tg_send(chat, "Use /start", kb_main())


# ============================================================
# POLL LOOP
# ============================================================
def poll():
    off = int(kv_get("tg_offset", "0") or "0")
    log(f"poll thread started (offset={off})")
    while True:
        try:
            r = requests.get(f"{TG_API}/getUpdates",
                params={"offset": off, "timeout": 25,
                        "allowed_updates":
                            json.dumps(["message", "callback_query"])},
                timeout=35)
            dd = r.json()
            if not dd.get("ok"):
                log("bad", dd); time.sleep(3); continue
            for u in dd.get("result", []):
                off = u["update_id"] + 1
                kv_set("tg_offset", str(off))
                try:
                    if "callback_query" in u:
                        cb(u["callback_query"])
                    elif "message" in u:
                        msg(u["message"])
                except Exception as e:
                    log("upd", e, traceback.format_exc())
        except requests.exceptions.ReadTimeout:
            continue
        except Exception as e:
            log("poll err", e); time.sleep(3)


def tg_boot():
    while True:
        try:
            if CHAT_ID:
                tg_send(CHAT_ID, f"🚀 Reward Bro Bot v{VERSION} online")
            poll()
        except Exception as e:
            log("tg_boot crashed, retry in 10s:", e)
            time.sleep(10)


# ============================================================
# FLASK
# ============================================================
app = Flask(__name__)


@app.route("/")
@app.route("/health")
def index():
    return "Active", 200


@app.route("/status")
def status():
    return jsonify({
        "ok": True,
        "version": VERSION,
        "accounts": len(db_list()),
        "uptime_sec": int(time.time() - START_TIME),
        "time": datetime.utcnow().isoformat() + "Z"
    })


@app.route("/stop")
def stop():
    os._exit(1)


# ============================================================
# ENTRY
# ============================================================
if __name__ == "__main__":
    threading.Thread(target=tg_boot, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, threaded=True)
