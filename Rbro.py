import os, json, time, sqlite3, threading
import traceback, requests, urllib3
from datetime import datetime
from flask import Flask, jsonify

urllib3.disable_warnings()

# ============ HARDCODED ============
BOT_TOKEN = "8890014279:AAGuKNVfg2WJ21DXCS_kBXgVlexjRxXUhL8"
CHAT_ID   = "1827265590"
# ===================================

PORT    = int(os.environ.get("PORT", "10000"))
DB_PATH = os.environ.get("DB_PATH", "/data/accounts.db")
if not os.path.isdir(os.path.dirname(DB_PATH)):
    DB_PATH = "accounts.db"
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

VERSION = "1.0.17"
START_TIME = time.time()

GEM_URL   = "https://us-central1-cash-bro-8c96e.cloudfunctions.net/claimGems"
SUPER_URL = "https://us-central1-cash-bro-8c96e.cloudfunctions.net/claimSuperOffer"
GEM_VALUE   = "10"
GEM_CLAIMS  = 20
SUPER_VALUE = "200"
GEM_DELAY   = 2

INSTANCE_ID = ("c83aRHv6QD6dgvLIVax39r:APA91bEpVaezbqZEx5L-qi8LgyiVQ8pD_s8c1i"
               "FcuYCLH0CXTvVeimRT3owoNKIEvfB2vAw1yHsQBdrFnExDU-q6ksGxKzFqr_lR"
               "dQhaJHTCx9XM7zYbdGY")

RE_BASE    = "https://app.rewardbro.in"
RE_API_KEY = "rb_live_9f3c7a21d8b64e5ab4c2f1e98d6a73c5f0b"
RE_DELAY   = 15

def log(*a):
    print(f"[{datetime.utcnow():%H:%M:%S}]", *a, flush=True)

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
        x.execute("INSERT INTO acc(name,bearer,appcheck,uid,at) "
                  "VALUES(?,?,?,?,?)",
                  (name, bearer, appcheck, uid,
                   datetime.utcnow().isoformat()))
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
        x.execute("SELECT id,name,bearer,appcheck,uid FROM acc WHERE id=?",
                  (i,))
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
    d = {"chat_id": cid, "text": t, "parse_mode": "Markdown"}
    if kb: d["reply_markup"] = json.dumps(kb)
    try: requests.post(f"{TG_API}/sendMessage", data=d, timeout=15)
    except Exception as e: log("tg_send", e)

def tg_edit(cid, mid, t, kb=None):
    d = {"chat_id": cid, "message_id": mid,
         "text": t, "parse_mode": "Markdown"}
    if kb: d["reply_markup"] = json.dumps(kb)
    try: requests.post(f"{TG_API}/editMessageText", data=d, timeout=15)
    except Exception as e: log("tg_edit", e)

def tg_ans(cbid, t=None):
    d = {"callback_query_id": cbid}
    if t: d["text"] = t
    try: requests.post(f"{TG_API}/answerCallbackQuery",
                       data=d, timeout=10)
    except Exception: pass

# ============================================================
# REWARD BRO API CALLS
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
        "gemsRequired": {
            "@type": "type.googleapis.com/google.protobuf.Int64Value",
            "value": SUPER_VALUE},
        "coins": {
            "@type": "type.googleapis.com/google.protobuf.Int64Value",
            "value": SUPER_VALUE}}}

def run_gems(acc, N):
    _, name, bearer, appcheck, uid = acc
    N(f"💎 claiming {GEM_VALUE} gems × {GEM_CLAIMS}")
    ok = 0
    for i in range(1, GEM_CLAIMS + 1):
        try:
            r = requests.post(GEM_URL,
                headers=gem_hdr(bearer, appcheck),
                json=gem_payload(), verify=False, timeout=30)
            if r.status_code == 401:
                N("❌ token expired"); return 0
            if r.status_code == 403:
                N("❌ appcheck rejected"); return 0
            if r.status_code == 200:
                ok += 1
                N(f"[{i}/{GEM_CLAIMS}] ✅")
            else:
                N(f"[{i}/{GEM_CLAIMS}] {r.status_code} {r.text[:80]}")
        except Exception as e:
            N(f"[{i}] 🚨 {e}")
        if i < GEM_CLAIMS:
            time.sleep(GEM_DELAY)
    N(f"✅ gems {ok}/{GEM_CLAIMS}")
    return ok

def run_super(acc, N):
    _, name, bearer, appcheck, uid = acc
    N(f"⚡ super offer ({SUPER_VALUE})")
    try:
        r = requests.post(SUPER_URL,
            headers=super_hdr(bearer, appcheck),
            json=super_payload(), verify=False, timeout=30)
        N(f"super → {r.status_code} | {r.text[:200]}")
    except Exception as e:
        N(f"🚨 super {e}")

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

def re_loop(acc, N):
    aid = acc[0]
    uid = acc[4]
    N(f"📖 Read & Earn ({RE_DELAY}s interval)")
    count = 0
    while aid not in STOPS:
        count += 1
        try:
            body = json.dumps({"appName": "rewardbro", "userId": uid})
            r = requests.request("GET",
                f"{RE_BASE}/get-read-earn-url",
                headers=re_hdr(), data=body,
                verify=False, timeout=30)
            if r.status_code != 200:
                N(f"[{count}] ❌ fetch {r.status_code}")
                time.sleep(RE_DELAY); continue
            data = r.json()
            if not data.get("success"):
                N(f"[{count}] ❌ {data.get('message')}")
                time.sleep(RE_DELAY); continue
            oid = data.get("offerId")
            coins = data.get("coins")
            lim = data.get("limits")
            done = data.get("completedCount")
            N(f"[{count}] 📥 offer={oid} coins={coins} {done}/{lim}")
            if lim is not None and done is not None and done >= lim:
                N("🏁 limit reached — stopping"); return
            for _ in range(RE_DELAY):
                if aid in STOPS: return
                time.sleep(1)
            pb = requests.get(
                f"{RE_BASE}/read-earn-postback",
                headers=re_hdr(),
                params={"appName": "rewardbro",
                        "userId": uid, "offerId": oid},
                verify=False, timeout=30)
            N(f"[{count}] 📤 {pb.status_code} {pb.text[:120]}")
        except Exception as e:
            N(f"[{count}] 🚨 {e}")
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
    def w():
        try: fn(*a)
        except Exception as e:
            log("job", e, traceback.format_exc())
        finally:
            JOBS[i] = False
            STOPS.discard(i)
    threading.Thread(target=w, daemon=True).start()
    return True

# ============================================================
# KEYBOARDS
# ============================================================
def kb_main():
    rows = []
    for i, n, u in db_list():
        pre = "🟢 " if running(i) else ""
        rows.append([{"text": f"{pre}#{i} {n}",
                      "callback_data": f"a:{i}"}])
    rows.append([{"text": "➕ Add Account", "callback_data": "add"}])
    rows.append([{"text": "🔄 Refresh", "callback_data": "home"}])
    return {"inline_keyboard": rows}

def kb_acc(i):
    rows = []
    if running(i):
        rows.append([{"text": "⏹ Stop", "callback_data": f"st:{i}"}])
    else:
        rows.append([{"text": "🚀 Run Full",
                      "callback_data": f"cf:{i}"}])
        rows.append([{"text": "💎 Gems Only",
                      "callback_data": f"cg:{i}"}])
        rows.append([{"text": "⚡ Super Only",
                      "callback_data": f"cs:{i}"}])
        rows.append([{"text": "📖 Read & Earn",
                      "callback_data": f"rs:{i}"}])
    rows.append([{"text": "🗑 Remove", "callback_data": f"x:{i}"}])
    rows.append([{"text": "◀️ Back", "callback_data": "home"}])
    return {"inline_keyboard": rows}

def kb_rm(i):
    return {"inline_keyboard": [
        [{"text": "✅ Yes", "callback_data": f"y:{i}"}],
        [{"text": "❌ No", "callback_data": f"a:{i}"}],
    ]}

# ============================================================
# TEXTS
# ============================================================
def menu_text():
    accs = db_list()
    L = [f"*Reward Bro Bot v{VERSION}*",
         f"Accounts: *{len(accs)}*", ""]
    if not accs:
        L.append("_No accounts. Tap ➕ Add._")
    else:
        for i, n, u in accs:
            pre = "🟢" if running(i) else "⚪"
            L.append(f"{pre} *#{i}* {n}")
    return "\n".join(L)

def acc_text(i):
    a = db_get(i)
    if not a: return "_not found_"
    _, name, bearer, appcheck, uid = a
    r = "🟢 running" if running(i) else "⚪ idle"
    tok = (bearer[:18] + "…") if bearer else "—"
    ck = (appcheck[:18] + "…") if appcheck else "—"
    return (f"*Reward Bro #{i} — {name}*\n"
            f"status: {r}\n\n"
            f"userId: `{uid}`\n"
            f"bearer: `{tok}`\n"
            f"appcheck: `{ck}`")

# ============================================================
# ADD-ACCOUNT 3-STEP FLOW
# ============================================================
def start_add(chat):
    kv_set(f"aw:{chat}", "add")
    kv_set(f"tmp:{chat}:bearer", "")
    kv_set(f"tmp:{chat}:appcheck", "")
    tg_send(chat,
        "➕ *Add Account — Step 1 of 3*\n\n"
        "Send *bearer token*:\n"
        "_(starts with `eyJ...`)_\n\n"
        "/cancel to abort",
        {"inline_keyboard":
            [[{"text": "❌ Cancel", "callback_data": "home"}]]})

def cancel_add(chat):
    kv_set(f"aw:{chat}", "")
    kv_set(f"tmp:{chat}:bearer", "")
    kv_set(f"tmp:{chat}:appcheck", "")

def handle_add_step(chat, t):
    bearer = kv_get(f"tmp:{chat}:bearer", "")
    appcheck = kv_get(f"tmp:{chat}:appcheck", "")

    if not bearer:
        if not t.startswith("eyJ"):
            tg_send(chat, "❌ Must start with `eyJ...`\nTry again:")
            return True
        kv_set(f"tmp:{chat}:bearer", t.replace("Bearer ", ""))
        tg_send(chat,
            "✅ Bearer saved\n\n"
            "➕ *Step 2 of 3*\n\n"
            "Send *appcheck* token:\n"
            "_(from `x-firebase-appcheck` header)_")
        return True

    if not appcheck:
        if not t.startswith("eyJ"):
            tg_send(chat, "❌ Must start with `eyJ...`\nTry again:")
            return True
        kv_set(f"tmp:{chat}:appcheck", t)
        tg_send(chat,
            "✅ AppCheck saved\n\n"
            "➕ *Step 3 of 3*\n\n"
            "Send *userId*:\n"
            "_(numbers or letters, no spaces)_")
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
        f"✅ *{name}* added (id #{new})\n\n"
        f"userId: `{uid}`\n"
        f"bearer: `{bearer[:18]}…`\n"
        f"appcheck: `{appcheck[:18]}…`",
        kb_main())
    return False

# ============================================================
# CALLBACKS
# ============================================================
def cb(c):
    cid = c["id"]
    chat = c["message"]["chat"]["id"]
    mid = c["message"]["message_id"]
    d = c.get("data", "")

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
        tg_edit(chat, mid, f"Remove *#{i}*?", kb_rm(i))
    elif d.startswith("y:"):
        i = int(d.split(":")[1])
        STOPS.add(i)
        ok = db_del(i)
        tg_ans(cid, "removed" if ok else "nope")
        tg_edit(chat, mid, menu_text(), kb_main())
    elif d.startswith("cf:"):
        i = int(d.split(":")[1]); tg_ans(cid, "…")
        a = db_get(i)
        if a:
            def N(m): tg_send(chat, f"*#{i}* {m}")
            spawn(i, run_full, a, N)
            tg_send(chat, f"*#{i}* 🚀 full run", kb_acc(i))
    elif d.startswith("cg:"):
        i = int(d.split(":")[1]); tg_ans(cid, "…")
        a = db_get(i)
        if a:
            def N(m): tg_send(chat, f"*#{i}* {m}")
            spawn(i, run_gems, a, N)
            tg_send(chat, f"*#{i}* 💎 gems", kb_acc(i))
    elif d.startswith("cs:"):
        i = int(d.split(":")[1]); tg_ans(cid, "…")
        a = db_get(i)
        if a:
            def N(m): tg_send(chat, f"*#{i}* {m}")
            spawn(i, run_super, a, N)
            tg_send(chat, f"*#{i}* ⚡ super", kb_acc(i))
    elif d.startswith("rs:"):
        i = int(d.split(":")[1]); tg_ans(cid, "…")
        a = db_get(i)
        if a:
            def N(m): tg_send(chat, f"*#{i}* {m}")
            spawn(i, re_loop, a, N)
            tg_send(chat, f"*#{i}* 📖 read&earn", kb_acc(i))
    elif d.startswith("st:"):
        i = int(d.split(":")[1]); tg_ans(cid, "stopping…")
        STOPS.add(i)
        tg_send(chat, f"*#{i}* ⏹ stop", kb_acc(i))
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
        tg_send(chat, "Cancelled", kb_main()); return

    if kv_get(f"aw:{chat}") == "add":
        handle_add_step(chat, t)
        return

    if t.startswith("/start") or t.startswith("/menu"):
        tg_send(chat, menu_text(), kb_main()); return
    if t.startswith("/add"):
        start_add(chat); return

    tg_send(chat, "Use /start", kb_main())

# ============================================================
# POLL LOOP
# ============================================================
def poll():
    off = 0
    log("poll thread started")
    while True:
        try:
            r = requests.get(f"{TG_API}/getUpdates",
                params={"offset": off, "timeout": 25,
                    "allowed_updates":
                        json.dumps(["message","callback_query"])},
                timeout=35)
            d = r.json()
            if not d.get("ok"):
                log("bad", d); time.sleep(3); continue
            for u in d.get("result", []):
                off = u["update_id"] + 1
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
def index():
    return "Active", 200

@app.route("/health")
def health():
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
