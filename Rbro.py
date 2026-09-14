import os, json, time, sqlite3, threading, html, traceback, requests, urllib3
from datetime import datetime
from flask import Flask, jsonify
urllib3.disable_warnings()

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8890014279:AAGuKNVfg2WJ21DXCS_kBXgVlexjRxXUhL8")
CHAT_ID   = os.environ.get("CHAT_ID", "1827265590")
PORT      = int(os.environ.get("PORT", "10000"))
DB_PATH   = os.environ.get("DB_PATH", "/data/accounts.db")
if not os.path.isdir(os.path.dirname(DB_PATH)): DB_PATH = "accounts.db"
TG = f"https://api.telegram.org/bot{BOT_TOKEN}"
VER = "1.2.1"; T0 = time.time()

GEM_URL   = "https://us-central1-cash-bro-8c96e.cloudfunctions.net/claimGems"
SUPER_URL = "https://us-central1-cash-bro-8c96e.cloudfunctions.net/claimSuperOffer"
GEM_V, GEM_N, SUPER_V, GEM_D = "10", 20, "200", 2
INSTANCE = "c83aRHv6QD6dgvLIVax39r:APA91bEpVaezbqZEx5L-qi8LgyiVQ8pD_s8c1iFcuYCLH0CXTvVeimRT3owoNKIEvfB2vAw1yHsQBdrFnExDU-q6ksGxKzFqr_lRdQhaJHTCx9XM7zYbdGY"
RE_BASE, RE_KEY, RE_D = "https://app.rewardbro.in", "rb_live_9f3c7a21d8b64e5ab4c2f1e98d6a73c5f0b", 15
STOP_W = ("daily limit","limit reached","limit exceed","limit crossed","no more offer",
          "no offers","completed all","all offers completed","quota","try again tomorrow")
MAX_FAIL = 3

log = lambda *a: print(f"[{datetime.utcnow():%H:%M:%S}]", *a, flush=True)
esc = lambda s: html.escape(str(s), quote=False)
def _i(x):
    try: return int(x)
    except: return None

# ---------- DB ----------
C = sqlite3.connect(DB_PATH, check_same_thread=False)
LK = threading.Lock()
x = C.cursor()
x.execute("CREATE TABLE IF NOT EXISTS acc(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,bearer TEXT,appcheck TEXT,uid TEXT,type TEXT DEFAULT 'gs',at TEXT)")
x.execute("CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT)")
try: x.execute("ALTER TABLE acc ADD COLUMN type TEXT DEFAULT 'gs'")
except: pass
C.commit()

def db_add(t, b, a, u):
    with LK:
        x = C.cursor(); x.execute("SELECT COUNT(*) FROM acc WHERE type=?", (t,)); n = (x.fetchone() or [0])[0] + 1
        nm = ("GS" if t == "gs" else "RD") + str(n)
        x.execute("INSERT INTO acc(name,bearer,appcheck,uid,type,at) VALUES(?,?,?,?,?,?)",
                  (nm, b, a, u, t, datetime.utcnow().isoformat())); C.commit()
        return x.lastrowid
def db_list(t=None):
    with LK:
        x = C.cursor()
        x.execute("SELECT id,name,uid FROM acc" + (" WHERE type=?" if t else "") + " ORDER BY id", (t,) if t else ())
        return x.fetchall()
def db_get(i):
    with LK:
        x = C.cursor(); x.execute("SELECT id,type,name,bearer,appcheck,uid FROM acc WHERE id=?", (i,)); return x.fetchone()
def db_del(i):
    with LK:
        x = C.cursor(); x.execute("DELETE FROM acc WHERE id=?", (i,)); C.commit(); return x.rowcount > 0
def kv_set(k, v):
    with LK:
        x = C.cursor(); x.execute("INSERT OR REPLACE INTO kv VALUES(?,?)", (k, v)); C.commit()
def kv_get(k, d=None):
    with LK:
        x = C.cursor(); x.execute("SELECT v FROM kv WHERE k=?", (k,)); r = x.fetchone(); return r[0] if r else d

# ---------- TG ----------
def tg_send(c, t, kb=None):
    d = {"chat_id": c, "text": t, "parse_mode": "HTML", "disable_web_page_preview": True}
    if kb: d["reply_markup"] = json.dumps(kb)
    try:
        r = requests.post(f"{TG}/sendMessage", data=d, timeout=15)
        if r.status_code != 200: log("send", r.status_code, r.text[:150])
    except Exception as e: log("send", e)
def tg_edit(c, m, t, kb=None):
    d = {"chat_id": c, "message_id": m, "text": t, "parse_mode": "HTML", "disable_web_page_preview": True}
    if kb: d["reply_markup"] = json.dumps(kb)
    try:
        r = requests.post(f"{TG}/editMessageText", data=d, timeout=15)
        if r.status_code != 200 and "not modified" not in r.text: log("edit", r.status_code, r.text[:150])
    except Exception as e: log("edit", e)
def tg_ans(cb, t=None):
    d = {"callback_query_id": cb}
    if t: d["text"] = t
    try: requests.post(f"{TG}/answerCallbackQuery", data=d, timeout=10)
    except: pass

# ---------- API ----------
def gh(b, a):
    return {"host":"us-central1-cash-bro-8c96e.cloudfunctions.net","authorization":f"Bearer {b}",
            "x-firebase-appcheck":a,"content-type":"application/json; charset=utf-8","user-agent":"okhttp/5.2.1"}
def sh(b, a): h = gh(b, a); h["firebase-instance-id-token"] = INSTANCE; return h
def gp(): return {"data":{"gems":{"@type":"type.googleapis.com/google.protobuf.Int64Value","value":GEM_V},"isInstall":False}}
def sp(): return {"data":{"gemsRequired":{"@type":"type.googleapis.com/google.protobuf.Int64Value","value":SUPER_V},
                          "coins":{"@type":"type.googleapis.com/google.protobuf.Int64Value","value":SUPER_V}}}
def _stop(txt):
    t = (txt or "").lower()
    for w in STOP_W:
        if w in t: return w
    return ""

def run_gems(a, N):
    aid, _, _, b, ck, _ = a; N(f"💎 {GEM_V} gems × {GEM_N}"); ok = 0
    for i in range(1, GEM_N + 1):
        if aid in STOPS: N(f"⏹ stopped @{i-1}"); return ok
        try:
            r = requests.post(GEM_URL, headers=gh(b, ck), json=gp(), verify=False, timeout=30)
            if r.status_code in (401, 403): N(f"❌ {r.status_code} — stop"); return ok
            if r.status_code == 200: ok += 1; N(f"[{i}/{GEM_N}] ✅")
            else:
                w = _stop(r.text); N(f"[{i}] {r.status_code} {esc(r.text[:60])}")
                if w: N(f"🏁 {w}"); return ok
        except Exception as e: N(f"[{i}] 🚨 {esc(e)}")
        for _ in range(GEM_D):
            if aid in STOPS: return ok
            time.sleep(1)
    N(f"✅ gems {ok}/{GEM_N}"); return ok

def run_super(a, N):
    aid, _, _, b, ck, _ = a
    if aid in STOPS: return
    N(f"⚡ super {SUPER_V}")
    try:
        r = requests.post(SUPER_URL, headers=sh(b, ck), json=sp(), verify=False, timeout=30)
        N(f"super → {r.status_code} | {esc(r.text[:150])}")
    except Exception as e: N(f"🚨 {esc(e)}")

def run_full(a, N):
    N("🚀 gem+super start"); run_gems(a, N)
    if a[0] in STOPS: N("🛑 stopped"); return
    time.sleep(GEM_D); run_super(a, N); N("🎯 done")

def re_h():
    return {"user-agent":"Dart/3.11 (dart:io)","content-type":"application/json","x-api-key":RE_KEY,
            "accept-encoding":"gzip","host":"app.rewardbro.in"}

def re_loop(a, N):
    aid, _, _, _, _, uid = a; N(f"📖 Reads ({RE_D}s)"); n = 0; f = 0
    while aid not in STOPS:
        n += 1
        try:
            r = requests.request("GET", f"{RE_BASE}/get-read-earn-url", headers=re_h(),
                                 data=json.dumps({"appName":"rewardbro","userId":uid}), verify=False, timeout=30)
            try: d = r.json()
            except: d = {}
            w = _stop(r.text) or _stop(json.dumps(d))
            if r.status_code == 429 or w: N(f"🏁 stop ({w or 'http 429'})"); return
            if r.status_code != 200 or not d.get("success"):
                f += 1; N(f"[{n}] ❌ {r.status_code} {esc(str(d.get('message'))[:60])}")
                if f >= MAX_FAIL: N(f"🏁 {f} fails"); return
                for _ in range(RE_D):
                    if aid in STOPS: return
                    time.sleep(1)
                continue
            f = 0
            oid, lim, done = d.get("offerId"), _i(d.get("limits")), _i(d.get("completedCount"))
            if lim and done is not None and lim > 0 and done >= lim:
                N(f"🏁 daily limit {done}/{lim}"); return
            if not oid: N("🏁 no offer"); return
            N(f"[{n}] 📥 {esc(oid)} coins={esc(d.get('coins'))} {done}/{lim}")
            for _ in range(RE_D):
                if aid in STOPS: return
                time.sleep(1)
            pb = requests.get(f"{RE_BASE}/read-earn-postback", headers=re_h(),
                              params={"appName":"rewardbro","userId":uid,"offerId":oid}, verify=False, timeout=30)
            N(f"[{n}] 📤 {pb.status_code} {esc(pb.text[:80])}")
        except Exception as e:
            f += 1; N(f"[{n}] 🚨 {esc(e)}")
            if f >= MAX_FAIL: N("🏁 too many errors"); return
        for _ in range(RE_D):
            if aid in STOPS: return
            time.sleep(1)
    N("🛑 stopped")

# ---------- JOBS ----------
JOBS, STOPS = {}, set()
running = lambda i: JOBS.get(i, False)
def spawn(i, fn, *a):
    with LK:
        if JOBS.get(i): return False
        JOBS[i] = True
    STOPS.discard(i)
    def w():
        try: fn(*a)
        except Exception as e: log("job", e, traceback.format_exc())
        finally:
            with LK: JOBS[i] = False
            STOPS.discard(i)
    threading.Thread(target=w, daemon=True).start(); return True

# ---------- KB ----------
def kb_main():
    return {"inline_keyboard":[
        [{"text":f"💎⚡ Gem+Super ({len(db_list('gs'))})","callback_data":"m:gs"}],
        [{"text":f"📖 Reads ({len(db_list('rd'))})","callback_data":"m:rd"}],
        [{"text":"🔄 Refresh","callback_data":"home"}]]}
def kb_list(t):
    rows = [[{"text":("🟢 " if running(i) else "") + f"#{i} {n}","callback_data":f"a:{t}:{i}"}]
            for i, n, u in db_list(t)]
    rows.append([{"text":f"➕ Add {'Gem+Super' if t=='gs' else 'Reads'}","callback_data":f"add:{t}"}])
    rows.append([{"text":"◀️ Back","callback_data":"home"}])
    return {"inline_keyboard":rows}
def kb_acc(i, t):
    rows = []
    if running(i): rows.append([{"text":"⏹ Stop","callback_data":f"st:{i}"}])
    else:
        if t == "gs":
            rows.append([{"text":f"🚀 Run {GEM_N}×Gems + Super","callback_data":f"r:full:{i}"}])
            rows.append([{"text":"💎 Gems Only","callback_data":f"r:g:{i}"},{"text":"⚡ Super Only","callback_data":f"r:s:{i}"}])
        else: rows.append([{"text":"📖 Start Reads","callback_data":f"r:rd:{i}"}])
    rows.append([{"text":"🗑 Remove","callback_data":f"x:{i}"}])
    rows.append([{"text":"◀️ Back","callback_data":f"m:{t}"}])
    return {"inline_keyboard":rows}
def kb_rm(i, back):
    return {"inline_keyboard":[[{"text":"✅ Yes","callback_data":f"y:{i}"}],[{"text":"❌ No","callback_data":back}]]}

def txt_main():
    return (f"<b>Reward Bro v{VER}</b>\n\n💎⚡ Gem+Super: <b>{len(db_list('gs'))}</b>\n"
            f"📖 Reads: <b>{len(db_list('rd'))}</b>\n\nPick an option:")
def txt_list(t):
    accs = db_list(t); L = [f"<b>{'💎⚡ Gem+Super' if t=='gs' else '📖 Reads'}</b>\n"]
    L += [f"{'🟢' if running(i) else '⚪'} <b>#{i}</b> {esc(n)}" for i, n, u in accs] if accs else ["<i>No accounts.</i>"]
    return "\n".join(L)
def txt_acc(i, t):
    a = db_get(i)
    if not a or a[1] != t: return "<i>not found</i>"
    _, _, nm, b, ck, uid = a
    r = "🟢 running" if running(i) else "⚪ idle"
    if t == "gs":
        return (f"<b>💎⚡ #{i} {esc(nm)}</b>\n{r}\nplan: {GEM_N}×{GEM_V} gems + {SUPER_V} super\n\n"
                f"bearer:   <code>{esc((b or '')[:18])}…</code>\nappcheck: <code>{esc((ck or '')[:18])}…</code>")
    return f"<b>📖 #{i} {esc(nm)}</b>\n{r}\n\nuserId: <code>{esc(uid)}</code>"

# ---------- ADD FLOW ----------
def cancel(chat): kv_set(f"aw:{chat}", ""); kv_set(f"step:{chat}", ""); kv_set(f"tmp:{chat}:b", ""); kv_set(f"tmp:{chat}:c", "")
def add_gs(chat):
    cancel(chat); kv_set(f"aw:{chat}", "gs"); kv_set(f"step:{chat}", "b")
    tg_send(chat, "➕ <b>Gem+Super — Step 1/2</b>\n\nSend <b>bearer</b> (<code>eyJ...</code>)\n\n/cancel to abort",
            {"inline_keyboard":[[{"text":"❌ Cancel","callback_data":"m:gs"}]]})
def add_rd(chat):
    cancel(chat); kv_set(f"aw:{chat}", "rd")
    tg_send(chat, "➕ <b>Reads</b>\n\nSend <b>userId</b>\n\n/cancel to abort",
            {"inline_keyboard":[[{"text":"❌ Cancel","callback_data":"m:rd"}]]})

def add_step(chat, t):
    k = kv_get(f"aw:{chat}"); s = kv_get(f"step:{chat}")
    if k == "gs":
        if s == "b":
            if not t.startswith("eyJ"): tg_send(chat, "❌ must start with <code>eyJ</code>"); return
            kv_set(f"tmp:{chat}:b", t.replace("Bearer ", "").strip()); kv_set(f"step:{chat}", "c")
            tg_send(chat, "✅ Bearer saved\n\n<b>Step 2/2</b>\nSend <b>appcheck</b>"); return
        if s == "c":
            if not t.startswith("eyJ"): tg_send(chat, "❌ must start with <code>eyJ</code>"); return
            b, c = kv_get(f"tmp:{chat}:b", ""), t.strip()
            nid = db_add("gs", b, c, ""); cancel(chat)
            tg_send(chat, f"✅ <b>Gem+Super #{nid}</b> added\nbearer: <code>{esc(b[:18])}…</code>\nappcheck: <code>{esc(c[:18])}…</code>", kb_list("gs")); return
    if k == "rd":
        uid = t.strip()
        if not uid or " " in uid or len(uid) > 100: tg_send(chat, "❌ invalid userId"); return
        nid = db_add("rd", "", "", uid); cancel(chat)
        tg_send(chat, f"✅ <b>Reads #{nid}</b> added\nuserId: <code>{esc(uid)}</code>", kb_list("rd"))

# ---------- CALLBACK ----------
def cb(c):
    cid, chat, mid, d = c["id"], c["message"]["chat"]["id"], c["message"]["message_id"], c.get("data","")
    if d == "home": cancel(chat); tg_ans(cid); tg_edit(chat, mid, txt_main(), kb_main())
    elif d in ("m:gs", "m:rd"):
        t = d.split(":")[1]; tg_ans(cid); tg_edit(chat, mid, txt_list(t), kb_list(t))
    elif d in ("add:gs", "add:rd"):
        tg_ans(cid); (add_gs if d.endswith("gs") else add_rd)(chat)
    elif d.startswith("a:"):
        _, t, i = d.split(":"); i = int(i); tg_ans(cid); tg_edit(chat, mid, txt_acc(i, t), kb_acc(i, t))
    elif d.startswith("x:"):
        i = int(d.split(":")[1]); a = db_get(i); back = "m:" + (a[1] if a else "gs")
        tg_ans(cid); tg_edit(chat, mid, f"Remove <b>#{i}</b>?", kb_rm(i, back))
    elif d.startswith("y:"):
        i = int(d.split(":")[1]); a = db_get(i)
        if running(i): STOPS.add(i); time.sleep(0.3)
        ok = db_del(i); tg_ans(cid, "removed" if ok else "nope")
        t = a[1] if a else "gs"; tg_edit(chat, mid, txt_list(t), kb_list(t))
    elif d.startswith("r:"):
        _, kind, i = d.split(":"); i = int(i); tg_ans(cid, "starting…")
        a = db_get(i)
        if not a: return
        t = a[1]
        want = {"full": "gs", "g": "gs", "s": "gs", "rd": "rd"}.get(kind)
        if t != want: return
        fn = {"full": run_full, "g": run_gems, "s": run_super, "rd": re_loop}.get(kind)
        def N(m, _i=i): tg_send(chat, f"<b>#{_i}</b> {m}")
        if fn and spawn(i, fn, a, N):
            tg_send(chat, f"<b>#{i}</b> 🚀 {kind} started", kb_acc(i, t))
        else: tg_send(chat, f"<b>#{i}</b> already running")
    elif d.startswith("st:"):
        i = int(d.split(":")[1]); tg_ans(cid, "stopping…")
        if running(i): STOPS.add(i); tg_send(chat, f"<b>#{i}</b> ⏹ stop sent")
        else: tg_send(chat, f"<b>#{i}</b> not running")
    else: tg_ans(cid)

# ---------- MSG ----------
def msg(m):
    chat, t = m["chat"]["id"], (m.get("text") or "").strip()
    if t == "/cancel": cancel(chat); tg_send(chat, "Cancelled", kb_main()); return
    if kv_get(f"aw:{chat}"):
        if t.startswith("/"): tg_send(chat, "⚠️ Send value or /cancel")
        else: add_step(chat, t)
        return
    if t.startswith(("/start", "/menu", "/help")): tg_send(chat, txt_main(), kb_main())
    elif t.startswith("/addgs"): add_gs(chat)
    elif t.startswith("/addrd"): add_rd(chat)
    else: tg_send(chat, "Use /start", kb_main())

# ---------- POLL ----------
def poll():
    off = int(kv_get("tg_offset", "0") or "0"); log("poll start", off)
    while True:
        try:
            r = requests.get(f"{TG}/getUpdates", params={"offset": off, "timeout": 25,
                "allowed_updates": json.dumps(["message", "callback_query"])}, timeout=35)
            dd = r.json()
            if not dd.get("ok"): time.sleep(3); continue
            for u in dd.get("result", []):
                off = u["update_id"] + 1; kv_set("tg_offset", str(off))
                try:
                    if "callback_query" in u: cb(u["callback_query"])
                    elif "message" in u: msg(u["message"])
                except Exception as e: log("upd", e)
        except requests.exceptions.ReadTimeout: continue
        except Exception as e: log("poll", e); time.sleep(3)

def boot():
    while True:
        try:
            if CHAT_ID: tg_send(CHAT_ID, f"🚀 Reward Bro v{VER} online")
            poll()
        except Exception as e: log("boot", e); time.sleep(10)

# ---------- FLASK ----------
app = Flask(__name__)

@app.route("/")
@app.route("/health")
def idx(): return "Active", 200

@app.route("/status")
def st(): return jsonify({"ok":True,"ver":VER,"gs":len(db_list("gs")),"rd":len(db_list("rd")),"up":int(time.time()-T0)})

if __name__ == "__main__":
    threading.Thread(target=boot, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, threaded=True)
