import os, json, time, base64, sqlite3, threading
import traceback, requests
from datetime import datetime
from flask import Flask, jsonify

# ============ HARDCODED CONFIG ============
BOT_TOKEN = "8817040407:AAHxM7D7l5Cc7yuIZvpaeS7guyIzQic9fQI"
CHAT_ID = "1827265590"
# ==========================================

PORT = int(os.environ.get("PORT", "10000"))
DB_PATH = os.environ.get("DB_PATH", "/data/accounts.db")
if not os.path.isdir(os.path.dirname(DB_PATH)):
    DB_PATH = "accounts.db"
BASE = "https://api.offerplay.in"
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
G_SURV = 35; G_AFTER = 5; AD_W = 20
I_W = 30; U_W = 125; C_GAP = 3; MARG = 5

INSTALL = {
    2:  ("com.vedantu.app", "Vedantu"),
    5:  ("com.phonepe.app", "PhonePe"),
    8:  ("in.swiggy.android", "Swiggy"),
    12: ("com.flipkart.android", "Flipkart"),
    15: ("com.myntra.android", "Myntra"),
    18: ("net.one97.paytm", "Paytm"),
}

def log(*a):
    print(f"[{datetime.utcnow():%H:%M:%S}]", *a, flush=True)

def db_init():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    x = c.cursor()
    x.execute("""CREATE TABLE IF NOT EXISTS accounts(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, token TEXT UNIQUE, uid TEXT, at TEXT)""")
    x.execute("""CREATE TABLE IF NOT EXISTS kv(
    k TEXT PRIMARY KEY, v TEXT)""")
    c.commit()
    return c

DB = db_init()
LK = threading.Lock()

def db_add(name, tok):
    uid = jwt_uid(tok)
    with LK:
        x = DB.cursor()
        try:
            x.execute("INSERT INTO accounts(name,token,uid,at)VALUES(?,?,?,?)",
                (name, tok, uid, datetime.utcnow().isoformat()))
            DB.commit()
            return x.lastrowid
        except sqlite3.IntegrityError:
            return None

def db_list():
    with LK:
        x = DB.cursor()
        x.execute("SELECT id,name,uid FROM accounts ORDER BY id")
        return x.fetchall()

def db_get(i):
    with LK:
        x = DB.cursor()
        x.execute("SELECT id,name,token,uid FROM accounts WHERE id=?", (i,))
        return x.fetchone()

def db_del(i):
    with LK:
        x = DB.cursor()
        x.execute("DELETE FROM accounts WHERE id=?", (i,))
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

def jwt_p(tok):
    try:
        s = tok.split(".")[1]
        s += "=" * (-len(s) % 4)
        return json.loads(base64.urlsafe_b64decode(s))
    except Exception as e:
        return {"err": str(e)}

def jwt_uid(tok):
    return jwt_p(tok).get("userId")

def jwt_days(tok):
    return (jwt_p(tok).get("exp", 0) - time.time()) / 86400

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
    try: requests.post(f"{TG_API}/answerCallbackQuery", data=d, timeout=10)
    except Exception: pass

def hdr(tok):
    return {
        "accept": "application/json, text/plain, */*",
        "authorization": f"Bearer {tok}",
        "x-platform": "android",
        "x-app-version": "81229",
        "x-is-rooted": "false",
        "x-is-emulator": "false",
        "x-device-fingerprint":
            "dev_248f03ee566cfa70|iQOO|I2301|15",
        "x-device-ua": "Mozilla/5.0 (Linux; Android 15; " +
            "I2301 Build/AP3A.240905.015.A2; wv) " +
            "AppleWebKit/537.36 (KHTML, like Gecko) " +
            "Version/4.0 Chrome/152.0.7977.88 Mobile Safari/537.36",
        "content-type": "application/json",
        "user-agent": "okhttp/4.10.0",
        "accept-encoding": "gzip",
    }

def api_get(tok, p):
    r = requests.get(BASE + p, headers=hdr(tok), timeout=30)
    return r.json()

def api_post(tok, p, b=None):
    r = requests.post(BASE + p, headers=hdr(tok),
                      json=b or {}, timeout=30)
    return r.json()

def gap(sec, label, N=None):
    if N: N(f"⏳ {sec}s — {label}")
    end = time.time() + sec
    while time.time() < end:
        time.sleep(min(5, max(.5, end - time.time())))
    if N: N(f"✅ {label}")

def status(tok):
    j = api_get(tok, "/api/superoffers/status")
    if not j.get("success"):
        raise RuntimeError(f"status {j}")
    return j["data"]

def iso_ms(s):
    if not s: return None
    try:
        return datetime.fromisoformat(
            s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None

def farm_1(tok, N=None):
    c = api_post(tok, "/api/ballmaxxing/gem-config", {})
    c = c.get("data", {}) or {}
    ms = c.get("milestones", [])
    idx = c.get("ladderClaimedIdx", -1)
    dt = c.get("dailyEarnedToday", 0)
    dc = c.get("dailyCap", 60)
    if dt >= dc:
        if N: N("⚠️ daily cap")
        return 0
    ni = idx + 1
    if ni >= len(ms):
        if N: N("⚠️ all rungs claimed")
        return 0
    sec, gm = ms[ni]
    w = sec + MARG
    if N: N(f"🎯 rung #{ni}: {sec}s → +{gm}💎")
    s = api_post(tok, "/api/ballmaxxing/start", {})
    if not s.get("success"):
        if N: N(f"❌ start {s}")
        return 0
    s = s["data"]
    gap(w, "run", N)
    r = api_post(tok, "/api/ballmaxxing/run", {
        "sessionId": s["sessionId"], "token": s["token"],
        "total": 3000, "surgeBonus": 0, "airBonus": 500,
        "survivalMs": w * 1000, "saves": 25,
        "revives": 0, "quit": False})
    d = r.get("data", {})
    aw = d.get("gemsAwarded", 0)
    if N: N(f"💎 +{aw} {d.get('gemDailyTotal')}/{d.get('gemDailyCap')}")
    return aw

def farm_until(tok, tgt, N=None):
    z = 0
    while True:
        st = status(tok)
        bal = st["currentGemBalance"]
        if bal >= tgt: return bal
        if N: N(f"farming bal={bal} need={tgt}")
        g = farm_1(tok, N)
        if g == 0:
            z += 1
            if z >= 3: return bal
            gap(5, "backoff", N)
        else:
            z = 0

def enter(tok, N=None):
    r = api_post(tok, "/api/superoffers/enter", {})
    if not r.get("success"):
        if N: N(f"❌ enter {r}")
        return None
    d = r["data"]
    if N: N(f"✅ #{d['attempt_id']} cost={d['gems_cost']}")
    return d["attempt_id"]

def do_game(tok, aid, N=None):
    gap(G_SURV, "game", N)
    api_post(tok, "/api/superoffers/game-complete", {
        "attempt_id": aid, "source": "ballmaxxing",
        "goals": 2500, "elapsed_sec": G_SURV})
    gap(G_AFTER, "register", N)

def do_ad(tok, aid, N=None):
    gap(AD_W, "ad", N)
    api_post(tok, "/api/superoffers/ad-complete",
             {"attempt_id": aid})

def do_inst(tok, aid, stg, N=None):
    pkg, nm = INSTALL.get(stg,
        (f"com.filler.app{stg}", f"App{stg}"))
    gap(I_W, f"install {nm}", N)
    api_post(tok, "/api/superoffers/install-detected", {
        "attempt_id": aid, "app_package": pkg, "app_name": nm})
    gap(U_W, "usage ≥120s", N)
    api_post(tok, "/api/superoffers/verify-usage", {
        "attempt_id": aid, "usage_minutes": 2})

def do_claim(tok, aid, uid, N=None):
    gap(C_GAP, "claim", N)
    sid = f"SO_{aid}_{uid}_{int(time.time()*1000)}"
    r = api_post(tok, "/api/superoffers/complete", {
        "attempt_id": aid, "spend_id": sid})
    d = r.get("data", {})
    if N:
        N(f"✅ coins={d.get('coins_awarded')} " +
          f"bal={d.get('new_coin_balance')} " +
          f"cd={d.get('cooldown_hours')}h")
    return d

def run_stage(acc, N=None):
    aid_a, name, tok, uid = acc
    def NN(m):
        if N: N(m)
    st = status(tok)
    ip = st.get("inProgressAttempt")
    if ip is None:
        if not st["canEnter"]:
            cd = iso_ms(st.get("cooldownEndsAt"))
            if cd and cd > time.time():
                w = int(cd - time.time()) + 2
                NN(f"🛏 cooldown {w}s")
                time.sleep(w)
            st = status(tok)
            if not st["canEnter"]:
                NN("❌ cannot enter")
                return False
        if st["currentGemBalance"] < st["gemsCost"]:
            farm_until(tok, st["gemsCost"], NN)
        a = enter(tok, NN)
        if not a: return False
        state = "pending"
    else:
        a = ip["id"]
        state = ip.get("status", "pending")
        NN(f"↩️ resume #{a} {state}")
    if state == "pending":
        do_game(tok, a, NN); state = "game_done"
    if state in ("pending", "game_done"):
        do_ad(tok, a, NN); state = "ad_watched"
    stg = st["attemptNumber"]
    inst = next((r["install"] for r in st["ladder"]
                 if r["stage"] == stg), False)
    if inst and state in ("pending", "game_done", "ad_watched"):
        do_inst(tok, a, stg, NN)
    do_claim(tok, a, uid, NN)
    return True

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
        finally: JOBS[i] = False
    threading.Thread(target=w, daemon=True).start()
    return True

def kb_main():
    rows = []
    for i, n, u in db_list():
        pre = "🟢 " if running(i) else ""
        rows.append([{"text": f"{pre}{n}",
                      "callback_data": f"a:{i}"}])
    rows.append([{"text": "➕ Add", "callback_data": "add"}])
    rows.append([{"text": "🔄 Refresh", "callback_data": "home"}])
    return {"inline_keyboard": rows}

def kb_acc(i):
    return {"inline_keyboard": [
        [{"text": "📊 Status", "callback_data": f"s:{i}"}],
        [{"text": "▶️ Run Next", "callback_data": f"n:{i}"}],
        [{"text": "🏁 Run All", "callback_data": f"r:{i}"}],
        [{"text": "💰 Farm", "callback_data": f"f:{i}"}],
        [{"text": "🗑 Remove", "callback_data": f"x:{i}"}],
        [{"text": "◀️ Back", "callback_data": "home"}],
    ]}

def kb_rm(i):
    return {"inline_keyboard": [
        [{"text": "✅ Yes", "callback_data": f"y:{i}"}],
        [{"text": "❌ No", "callback_data": f"a:{i}"}],
    ]}

def menu_text():
    accs = db_list()
    L = ["*Super Offer Bot*", f"Accounts: *{len(accs)}*", ""]
    if not accs:
        L.append("_No accounts. Tap ➕ Add._")
    else:
        for i, n, u in accs:
            r = " 🟢" if running(i) else ""
            L.append(f"• #{i} — *{n}*{r}")
    return "\n".join(L)

def acc_text(i):
    acc = db_get(i)
    if not acc: return "_not found_"
    _, n, tok, uid = acc
    d = jwt_days(tok)
    try:
        st = status(tok)
        s = st["attemptNumber"]; g = st["currentGemBalance"]
        ce = st["canEnter"]; cd = st.get("cooldownEndsAt") or "—"
        ip = st.get("inProgressAttempt")
        ipt = f"`{ip['status']}` id={ip['id']}" if ip else "—"
    except Exception as e:
        s = g = "?"; ce = False; cd = f"err"; ipt = "—"
    r = "🟢 RUNNING" if running(i) else "⚪ idle"
    return (f"*#{i} — {n}*\n"
            f"uid: `{uid}`\n"
            f"token: {d:.1f}d left\n"
            f"status: {r}\n\n"
            f"stage: {s}/20\n"
            f"gems: {g}\n"
            f"canEnter: {ce}\n"
            f"cooldown: {cd}\n"
            f"inProgress: {ipt}")

def cb(c):
    cid = c["id"]
    chat = c["message"]["chat"]["id"]
    mid = c["message"]["message_id"]
    d = c.get("data", "")
    if d == "home":
        tg_ans(cid)
        tg_edit(chat, mid, menu_text(), kb_main())
    elif d == "add":
        tg_ans(cid)
        kv_set(f"aw:{chat}", "add")
        tg_edit(chat, mid,
            "Send: `name | token`\n\n/cancel to abort.",
            {"inline_keyboard":
                [[{"text": "❌ Cancel", "callback_data": "home"}]]})
    elif d.startswith("a:"):
        i = int(d.split(":")[1]); tg_ans(cid)
        tg_edit(chat, mid, acc_text(i), kb_acc(i))
    elif d.startswith("s:"):
        i = int(d.split(":")[1])
        tg_ans(cid, "…")
        tg_edit(chat, mid, acc_text(i), kb_acc(i))
    elif d.startswith("x:"):
        i = int(d.split(":")[1]); tg_ans(cid)
        tg_edit(chat, mid, f"Remove #{i}?", kb_rm(i))
    elif d.startswith("y:"):
        i = int(d.split(":")[1])
        ok = db_del(i)
        tg_ans(cid, "done" if ok else "nope")
        tg_edit(chat, mid, menu_text(), kb_main())
    elif d.startswith("n:"):
        i = int(d.split(":")[1]); tg_ans(cid, "…")
        go_next(chat, i)
    elif d.startswith("r:"):
        i = int(d.split(":")[1]); tg_ans(cid, "…")
        go_all(chat, i)
    elif d.startswith("f:"):
        i = int(d.split(":")[1]); tg_ans(cid, "…")
        go_farm(chat, i)
    else:
        tg_ans(cid)

def go_next(chat, i):
    a = db_get(i)
    if not a:
        tg_send(chat, "not found"); return
    def N(m): tg_send(chat, f"*#{i}* {m}")
    def j():
        tg_send(chat, f"*#{i}* ▶️ next…")
        try:
            ok = run_stage(a, N)
            tg_send(chat, f"*#{i}* {'✅' if ok else '❌'}")
        except Exception as e:
            tg_send(chat, f"*#{i}* 💥 {e}")
    if not spawn(i, j):
        tg_send(chat, f"*#{i}* busy")

def go_all(chat, i):
    a = db_get(i)
    if not a:
        tg_send(chat, "not found"); return
    def N(m): tg_send(chat, f"*#{i}* {m}")
    def j():
        tg_send(chat, f"*#{i}* 🏁 all…")
        while True:
            try:
                st = status(a[2])
                if st["attemptNumber"] > 20 or st.get("weekComplete"):
                    tg_send(chat, f"*#{i}* 🎉 done"); return
                ok = run_stage(a, N)
                if not ok:
                    tg_send(chat, f"*#{i}* ❌ stop"); return
                st = status(a[2])
                cd = iso_ms(st.get("cooldownEndsAt"))
                if cd and cd > time.time():
                    w = int(cd - time.time()) + 2
                    N(f"🛏 {w}s")
                    time.sleep(w)
            except Exception as e:
                tg_send(chat, f"*#{i}* 💥 {e}"); return
    if not spawn(i, j):
        tg_send(chat, f"*#{i}* busy")

def go_farm(chat, i):
    a = db_get(i)
    if not a:
        tg_send(chat, "not found"); return
    def N(m): tg_send(chat, f"*#{i}* {m}")
    def j():
        tg_send(chat, f"*#{i}* 💰 farm…")
        try:
            b = farm_until(a[2], 999, N)
            tg_send(chat, f"*#{i}* bal={b}")
        except Exception as e:
            tg_send(chat, f"*#{i}* 💥 {e}")
    if not spawn(i, j):
        tg_send(chat, f"*#{i}* busy")

def msg(m):
    chat = m["chat"]["id"]
    t = (m.get("text") or "").strip()
    if t == "/cancel":
        kv_set(f"aw:{chat}", "")
        tg_send(chat, "Cancelled", kb_main()); return
    if kv_get(f"aw:{chat}") == "add":
        if "|" not in t:
            tg_send(chat, "Format: `name | token`"); return
        n, tok = [p.strip() for p in t.split("|", 1)]
        if not n or not tok:
            tg_send(chat, "Need both"); return
        uid = jwt_uid(tok)
        if not uid:
            tg_send(chat, "❌ Bad token"); return
        new = db_add(n, tok)
        kv_set(f"aw:{chat}", "")
        if new is None:
            tg_send(chat, "❌ Duplicate")
        else:
            tg_send(chat, f"✅ #{new} {n}\nuid: `{uid}`", kb_main())
        return
    if t.startswith("/start") or t.startswith("/accounts"):
        tg_send(chat, menu_text(), kb_main()); return
    if t.startswith("/add"):
        kv_set(f"aw:{chat}", "add")
        tg_send(chat, "Send `name | token`"); return
    tg_send(chat, "Use /start", kb_main())

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

app = Flask(__name__)

@app.route("/")
def root():
    return jsonify({"ok": True,
        "accounts": len(db_list()),
        "time": datetime.utcnow().isoformat() + "Z"})

@app.route("/health")
def health():
    return "ok", 200

@app.route(f"/tg/{BOT_TOKEN}", methods=["POST"])
def wh():
    return "ok", 200

@app.route("/run/<int:i>")
def http_run(i):
    a = db_get(i)
    if not a: return jsonify({"err": "nf"}), 404
    if running(i): return jsonify({"err": "busy"}), 409
    def j():
        try: run_stage(a, lambda m: log(f"#{i} {m}"))
        except Exception as e: log("hr", e)
    spawn(i, j)
    return jsonify({"ok": True, "id": i})

def boot():
    if not BOT_TOKEN:
        log("⚠️ BOT_TOKEN missing")
    else:
        threading.Thread(target=poll, daemon=True).start()
        # Send a startup message to your chat
        if CHAT_ID:
            tg_send(CHAT_ID, "🚀 Bot started")
    log("boot ok db=", DB_PATH)

boot()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
