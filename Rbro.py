import os, json, time, sqlite3, threading
import traceback, requests
from datetime import datetime
from flask import Flask, jsonify

# ============ HARDCODED ============
BOT_TOKEN = "8890014279:AAGuKNVfg2WJ21DXCS_kBXgVlexjRxXUhL8"
CHAT_ID   = "1827265590"
# ===================================

PORT    = int(os.environ.get("PORT", "10000"))
DB_PATH = os.environ.get("DB_PATH", "/data/accounts.db")
if not os.path.isdir(os.path.dirname(DB_PATH)):
    DB_PATH = "accounts.db"
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

VERSION = "1.0.15"

# ---- Cash Bro ----
CB_GEM_URL   = "https://us-central1-cash-bro-8c96e.cloudfunctions.net/claimGems"
CB_SUPER_URL = "https://us-central1-cash-bro-8c96e.cloudfunctions.net/claimSuperOffer"
GEM_VALUE    = "10"
GEM_CLAIMS   = 20
SUPER_VALUE  = "200"
CB_DELAY     = 2

INSTANCE_ID = ("c83aRHv6QD6dgvLIVax39r:APA91bEpVaezbqZEx5L-qi8LgyiVQ8pD_s8c1i"
               "FcuYCLH0CXTvVeimRT3owoNKIEvfB2vAw1yHsQBdrFnExDU-q6ksGxKzFqr_lR"
               "dQhaJHTCx9XM7zYbdGY")

# ---- Reward Bro ----
RB_BASE    = "https://app.rewardbro.in"
RB_API_KEY = "rb_live_9f3c7a21d8b64e5ab4c2f1e98d6a73c5f0b"
RB_DELAY   = 15

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
    kind TEXT,
    name TEXT,
    bearer TEXT,
    appcheck TEXT,
    uid TEXT,
    at TEXT)""")
    x.execute("""CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT)""")
    c.commit()
    return c

DB = db_init()
LK = threading.Lock()

def db_add(kind, name, bearer="", appcheck="", uid=""):
    with LK:
        x = DB.cursor()
        x.execute("INSERT INTO acc(kind,name,bearer,appcheck,uid,at)"
                  "VALUES(?,?,?,?,?,?)",
                  (kind, name, bearer, appcheck, uid,
                   datetime.utcnow().isoformat()))
        DB.commit()
        return x.lastrowid

def db_list(kind=None):
    with LK:
        x = DB.cursor()
        if kind:
            x.execute("SELECT id,kind,name,uid FROM acc "
                      "WHERE kind=? ORDER BY id", (kind,))
        else:
            x.execute("SELECT id,kind,name,uid FROM acc ORDER BY id")
        return x.fetchall()

def db_get(i):
    with LK:
        x = DB.cursor()
        x.execute("SELECT id,kind,name,bearer,appcheck,uid "
                  "FROM acc WHERE id=?", (i,))
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
# CASH BRO
# ============================================================
def cb_gem_headers(bearer, appcheck):
    return {
        "host": "us-central1-cash-bro-8c96e.cloudfunctions.net",
        "authorization": f"Bearer {bearer}",
        "x-firebase-appcheck": appcheck,
        "content-type": "application/json; charset=utf-8",
        "user-agent": "okhttp/5.2.1",
    }

def cb_super_headers(bearer, appcheck):
    h = cb_gem_headers(bearer, appcheck)
    h["firebase-instance-id-token"] = INSTANCE_ID
    return h

def cb_gem_payload():
    return {"data": {"gems": {
        "@type": "type.googleapis.com/google.protobuf.Int64Value",
        "value": GEM_VALUE}, "isInstall": False}}

def cb_super_payload():
    return {"data": {
        "gemsRequired": {
            "@type": "type.googleapis.com/google.protobuf.Int64Value",
            "value": SUPER_VALUE},
        "coins": {
            "@type": "type.googleapis.com/google.protobuf.Int64Value",
            "value": SUPER_VALUE}}}

def cb_run_gems(acc, N):
    _, kind, name, bearer, appcheck, uid = acc
    N(f"💎 claiming {GEM_VALUE} gems × {GEM_CLAIMS}")
    ok = 0
    for i in range(1, GEM_CLAIMS + 1):
        try:
            r = requests.post(CB_GEM_URL,
                headers=cb_gem_headers(bearer, appcheck),
                json=cb_gem_payload(), verify=False, timeout=30)
            code = r.status_code
            txt = r.text[:120]
            if code == 401:
                N("❌ token expired"); return 0
            if code == 403:
                N("❌ appcheck rejected"); return 0
            if code == 200:
                ok += 1
                N(f"[{i}/{GEM_CLAIMS}] ✅")
            else:
                N(f"[{i}/{GEM_CLAIMS}] {code} {txt}")
        except Exception as e:
            N(f"[{i}] 🚨 {e}")
        if i < GEM_CLAIMS:
            time.sleep(CB_DELAY)
    N(f"✅ gems {ok}/{GEM_CLAIMS}")
    return ok

def cb_run_super(acc, N):
    _, kind, name, bearer, appcheck, uid = acc
    N(f"⚡ claiming super offer ({SUPER_VALUE})")
    try:
        r = requests.post(CB_SUPER_URL,
            headers=cb_super_headers(bearer, appcheck),
            json=cb_super_payload(), verify=False, timeout=30)
        N(f"super: {r.status_code} | {r.text[:200]}")
    except Exception as e:
        N(f"🚨 super {e}")

def cb_run_full(acc, N):
    N("🚀 Cash Bro — full run")
    cb_run_gems(acc, N)
    time.sleep(CB_DELAY)
    cb_run_super(acc, N)
    N("🎯 done")

# ============================================================
# REWARD BRO
# ============================================================
STOPS = set()   # account ids requested to stop

def rb_headers():
    return {
        "user-agent": "Dart/3.11 (dart:io)",
        "content-type": "application/json",
        "x-api-key": RB_API_KEY,
        "accept-encoding": "gzip",
        "host": "app.rewardbro.in",
    }

def rb_loop(acc, N):
    aid = acc[0]
    uid = acc[5]
    N(f"📖 Read & Earn loop starting ({RB_DELAY}s)")
    count = 0
    while aid not in STOPS:
        count += 1
        try:
            body = json.dumps({"appName": "rewardbro", "userId": uid})
            r = requests.request("GET",
                f"{RB_BASE}/get-read-earn-url",
                headers=rb_headers(), data=body,
                verify=False, timeout=30)
            if r.status_code != 200:
                N(f"[{count}] ❌ fetch {r.status_code} {r.text[:100]}")
                time.sleep(RB_DELAY); continue
            data = r.json()
            if not data.get("success"):
                N(f"[{count}] ❌ {data.get('message')}")
                time.sleep(RB_DELAY); continue
            oid = data.get("offerId")
            coins = data.get("coins")
            lim = data.get("limits")
            done = data.get("completedCount")
            N(f"[{count}] 📥 offer={oid} coins={coins} {done}/{lim}")
            if lim is not None and done is not None and done >= lim:
                N(f"🏁 limit reached — stopping"); return
            # wait then postback
            for _ in range(RB_DELAY):
                if aid in STOPS: return
                time.sleep(1)
            pb = requests.get(
                f"{RB_BASE}/read-earn-postback",
                headers=rb_headers(),
                params={"appName": "rewardbro",
                        "userId": uid, "offerId": oid},
                verify=False, timeout=30)
            N(f"[{count}] 📤 {pb.status_code} {pb.text[:120]}")
        except Exception as e:
            N(f"[{count}] 🚨 {e}")
        for _ in range(RB_DELAY):
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
    for i, k, n, u in db_list():
        pre = "🟢 " if running(i) else ""
        tag = "⚡" if k == "cashbro" else "📖"
        rows.append([{"text": f"{pre}{tag} #{i} {n}",
                      "callback_data": f"a:{i}"}])
    rows.append([{"text": "➕ Add Cash Bro", "callback_data": "addcb"}])
    rows.append([{"text": "➕ Add Reward Bro", "callback_data": "addrb"}])
    rows.append([{"text": "🔄 Refresh", "callback_data": "home"}])
    return {"inline_keyboard": rows}

def kb_cb(i):
    return {"inline_keyboard": [
        [{"text": "🚀 Run Full", "callback_data": f"cf:{i}"}],
        [{"text": "💎 Gems Only", "callback_data": f"cg:{i}"}],
        [{"text": "⚡ Super Only", "callback_data": f"cs:{i}"}],
        [{"text": "🗑 Remove", "callback_data": f"x:{i}"}],
        [{"text": "◀️ Back", "callback_data": "home"}],
    ]}

def kb_rb(i):
    rows = []
    if running(i):
        rows.append([{"text": "⏹ Stop", "callback_data": f"st:{i}"}])
    else:
        rows.append([{"text": "▶️ Start Loop", "callback_data": f"rs:{i}"}])
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
    L = [f"*Multi Tool Bot v{VERSION}*",
         f"Accounts: *{len(accs)}*", ""]
    if not accs:
        L.append("_No accounts. Tap ➕ Add._")
    else:
        for i, k, n, u in accs:
            pre = "🟢" if running(i) else "⚪"
            tag = "⚡" if k == "cashbro" else "📖"
            L.append(f"{pre} {tag} *#{i}* {n}")
    return "\n".join(L)

def acc_text(i):
    a = db_get(i)
    if not a: return "_not found_"
    _, kind, name, bearer, appcheck, uid = a
    r = "🟢 running" if running(i) else "⚪ idle"
    if kind == "cashbro":
        tok = (bearer[:20] + "…") if bearer else "—"
        ck = (appcheck[:20] + "…") if appcheck else "—"
        return (f"*⚡ Cash Bro #{i}*\n"
                f"name: {name}\n"
                f"status: {r}\n\n"
                f"bearer: `{tok}`\n"
                f"appcheck: `{ck}`")
    else:
        return (f"*📖 Reward Bro #{i}*\n"
                f"name: {name}\n"
                f"status: {r}\n\n"
                f"userId: `{uid}`")

# ============================================================
# CALLBACKS
# ============================================================
def cb(c):
    cid = c["id"]
    chat = c["message"]["chat"]["id"]
    mid = c["message"]["message_id"]
    d = c.get("data", "")

    if d == "home":
        tg_ans(cid)
        tg_edit(chat, mid, menu_text(), kb_main())
    elif d == "addcb":
        tg_ans(cid)
        kv_set(f"aw:{chat}", "addcb")
        tg_edit(chat, mid,
            "*Add Cash Bro*\n\nSend 2 lines:\n"
            "`bearer`\n`appcheck`\n\nor /cancel",
            {"inline_keyboard":
                [[{"text": "❌ Cancel", "callback_data": "home"}]]})
    elif d == "addrb":
        tg_ans(cid)
        kv_set(f"aw:{chat}", "addrb")
        tg_edit(chat, mid,
            "*Add Reward Bro*\n\nSend user ID:\n`12345`\n\nor /cancel",
            {"inline_keyboard":
                [[{"text": "❌ Cancel", "callback_data": "home"}]]})
    elif d.startswith("a:"):
        i = int(d.split(":")[1]); tg_ans(cid)
        a = db_get(i)
        if not a:
            tg_edit(chat, mid, "_gone_", kb_main()); return
        kb = kb_cb(i) if a[1] == "cashbro" else kb_rb(i)
        tg_edit(chat, mid, acc_text(i), kb)
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
        if not a: return
        def N(m): tg_send(chat, f"*CB#{i}* {m}")
        spawn(i, cb_run_full, a, N)
    elif d.startswith("cg:"):
        i = int(d.split(":")[1]); tg_ans(cid, "…")
        a = db_get(i)
        if not a: return
        def N(m): tg_send(chat, f"*CB#{i}* {m}")
        spawn(i, cb_run_gems, a, N)
    elif d.startswith("cs:"):
        i = int(d.split(":")[1]); tg_ans(cid, "…")
        a = db_get(i)
        if not a: return
        def N(m): tg_send(chat, f"*CB#{i}* {m}")
        spawn(i, cb_run_super, a, N)
    elif d.startswith("rs:"):
        i = int(d.split(":")[1]); tg_ans(cid, "…")
        a = db_get(i)
        if not a: return
        def N(m): tg_send(chat, f"*RB#{i}* {m}")
        spawn(i, rb_loop, a, N)
    elif d.startswith("st:"):
        i = int(d.split(":")[1]); tg_ans(cid, "stopping…")
        STOPS.add(i)
        tg_send(chat, f"*RB#{i}* ⏹ stop requested")
    else:
        tg_ans(cid)

# ============================================================
# MESSAGES
# ============================================================
def msg(m):
    chat = m["chat"]["id"]
    t = (m.get("text") or "").strip()
    if t == "/cancel":
        kv_set(f"aw:{chat}", "")
        tg_send(chat, "Cancelled", kb_main()); return
    aw = kv_get(f"aw:{chat}")
    if aw == "addcb":
        lines = [x.strip() for x in t.splitlines() if x.strip()]
        if len(lines) < 2:
            tg_send(chat, "Send 2 lines:\n`bearer`\n`appcheck`"); return
        bearer, appcheck = lines[0].replace("Bearer ", ""), lines[1]
        n = len(db_list("cashbro")) + 1
        name = f"CB{n}"
        new = db_add("cashbro", name, bearer, appcheck)
        kv_set(f"aw:{chat}", "")
        tg_send(chat, f"✅ *{name}* added (#{new})", kb_main())
        return
    if aw == "addrb":
        if not t:
            tg_send(chat, "Send user ID"); return
        n = len(db_list("rewardbro")) + 1
        name = f"RB{n}"
        new = db_add("rewardbro", name, uid=t)
        kv_set(f"aw:{chat}", "")
        tg_send(chat, f"✅ *{name}* added (#{new})", kb_main())
        return
    if t.startswith("/start") or t.startswith("/menu"):
        tg_send(chat, menu_text(), kb_main()); return
    if t.startswith("/addcb"):
        kv_set(f"aw:{chat}", "addcb")
        tg_send(chat, "Send 2 lines:\n`bearer`\n`appcheck`"); return
    if t.startswith("/addrb"):
        kv_set(f"aw:{chat}", "addrb")
        tg_send(chat, "Send user ID:"); return
    tg_send(chat, "Use /start", kb_main())

# ============================================================
# POLL
# ============================================================
def poll():
    off = 0
    log("poll start")
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
            log("poll", e); time.sleep(3)

# ============================================================
# FLASK
# ============================================================
app = Flask(__name__)

@app.route("/")
def root():
    return jsonify({"ok": True, "v": VERSION,
        "accounts": len(db_list()),
        "time": datetime.utcnow().isoformat() + "Z"})

@app.route("/health")
def health():
    return "ok", 200

def boot():
    if not BOT_TOKEN:
        log("⚠️ no BOT_TOKEN"); return
    threading.Thread(target=poll, daemon=True).start()
    if CHAT_ID:
        tg_send(CHAT_ID, f"🚀 Multi Tool Bot v{VERSION} started")
    log("boot ok db=", DB_PATH)

boot()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
