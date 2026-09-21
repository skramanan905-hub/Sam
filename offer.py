import os,json,time,base64,sqlite3,threading,traceback,requests
from datetime import datetime
from flask import Flask,jsonify

BOT_TOKEN="8817040407:AAHxM7D7l5Cc7yuIZvpaeS7guyIzQic9fQI"
CHAT_ID="1827265590"
SEED_TOKENS=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiJjbXUwbGZhdnIxcG85a3k2azViZW9mcWg1IiwiaWF0IjoxNzg5MzUxMDY2LCJleHAiOjE3OTE5NDMwNjZ9.1gDFvfLFsPVV9Lu6lE6bAV4hB4hcplIepkSLhUm26vg","eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiJjbXUwbGt6a3YxcmV1a3k2a2JlZGo1OWc1IiwiaWF0IjoxNzg5MzUxMzMxLCJleHAiOjE3OTE5NDMzMzF9.mBFfNWWKkKXo6YbqMqw4YyolzLJz-MWuYYp0dwZCCS8","eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiJjbXUwbG44MGcxcnpqa3k2a3Y1MHJwcDRvIiwiaWF0IjoxNzg5MzUxNDM1LCJleHAiOjE3OTE5NDM0MzV9.JNxoy9OfVRku0093e8ghJMdTqi2FsyVbFd8KLbwOShM","eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiJjbXUwbHEyMmsxc3Awa3k2a25ia3QydHdkIiwiaWF0IjoxNzg5MzUxNTY4LCJleHAiOjE3OTE5NDM1Njh9.dINBH6n5VdgjBhLcNlF5J5yveNzP96e-qIkmSuWQ4g4","eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiJjbXUwbHRvZWMxdHZ0a3k2a2Q2cWh1YXo4IiwiaWF0IjoxNzg5MzUxNzM3LCJleHAiOjE3OTE5NDM3Mzd9.1bU1CmavJwsRWPynO3QYqbBKfMxbCEumYMcj7zbxVoY","eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiJjbXUwbHdxMjMxdW45a3k2azl1YjB5MjJmIiwiaWF0IjoxNzg5MzUxODc5LCJleHAiOjE3OTE5NDM4Nzl9.OBC-T7FwG1cNozso_3aZgylOg-n6mcXqeD3I1FxEyfw","eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiJjbXUwbHozYmQxdm1la3k2azd1cWhidm5nIiwiaWF0IjoxNzg5MzUxOTg5LCJleHAiOjE3OTE5NDM5ODl9.g6BVh2TBbZhs5N5CiL1Pi2PCvtIZGO3T9lbrYlMZ3eE","eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiJjbXUwbTI2MG8xd2dka3k2azJnenY5YXFkIiwiaWF0IjoxNzg5MzUyMTMzLCJleHAiOjE3OTE5NDQxMzN9.lT-Mzi3bfzbjxU4pV1EzViBA8YymFpctQ355geRilqs","eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiJjbXUwbTN1dGYxeDRla3k2azBwNDVyY2l1IiwiaWF0IjoxNzg5MzUyMjExLCJleHAiOjE3OTE5NDQyMTF9.7MZulw3MWnf_rF8rH8ggG0e6sRi6u-3LbdVX4_9kfps","eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiJjbXUwbTVudm4xeHBua3k2a3VtMmg2OGJwIiwiaWF0IjoxNzg5MzUyMjk2LCJleHAiOjE3OTE5NDQyOTZ9.l9dY6rFYQSLNazJ6th2gpjnqOMro-NCWX4g_SRxJjYU","eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiJjbXMwbWNjcWMzcDhuYmF5ZW1semVneGk2IiwiaWF0IjoxNzg5MjcxOTcxLCJleHAiOjE3OTE4NjM5NzF9.5hb6ruGKzkQ1YqBt4NggmjXttlWF_qMlqCfZqx1oMKw"]

PORT=int(os.environ.get("PORT","10000"))
DB_PATH=os.environ.get("DB_PATH","/data/accounts.db")
if not os.path.isdir(os.path.dirname(DB_PATH)):DB_PATH="accounts.db"
BASE="https://api.offerplay.in"
TG=f"https://api.telegram.org/bot{BOT_TOKEN}"
V="1.0.17";T0=time.time()
G_SURV=35;G_AFTER=5;AD_W=20;I_W=30;U_W=125;C_GAP=3;MARG=5
INSTALL={2:("org.coursera.android","Coursera"),5:("com.bigbasket.mobileapp","BigBasket"),8:("com.yubi.android.my.yubi.invest","Aspero"),12:("com.adobe.spark.post","Adobe Express"),15:("com.ril.shein","SHEIN")}

def log(*a):print(f"[{datetime.utcnow():%H:%M:%S}]",*a,flush=True)

def db_init():
    c=sqlite3.connect(DB_PATH,check_same_thread=False);x=c.cursor()
    x.execute("CREATE TABLE IF NOT EXISTS accounts(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,token TEXT UNIQUE,uid TEXT,at TEXT)")
    x.execute("CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY,v TEXT)")
    c.commit();return c
DB=db_init();LK=threading.Lock()

def db_add(n,t):
    u=jwt_uid(t)
    with LK:
        x=DB.cursor()
        try:
            x.execute("INSERT INTO accounts(name,token,uid,at)VALUES(?,?,?,?)",(n,t,u,datetime.utcnow().isoformat()))
            DB.commit();return x.lastrowid
        except sqlite3.IntegrityError:return None
def db_list():
    with LK:
        x=DB.cursor();x.execute("SELECT id,name,uid FROM accounts ORDER BY id");return x.fetchall()
def db_get(i):
    with LK:
        x=DB.cursor();x.execute("SELECT id,name,token,uid FROM accounts WHERE id=?",(i,));return x.fetchone()
def db_del(i):
    with LK:
        x=DB.cursor();x.execute("DELETE FROM accounts WHERE id=?",(i,));DB.commit();return x.rowcount>0
def kv_set(k,v):
    with LK:
        x=DB.cursor();x.execute("INSERT OR REPLACE INTO kv VALUES(?,?)",(k,v));DB.commit()
def kv_get(k,d=None):
    with LK:
        x=DB.cursor();x.execute("SELECT v FROM kv WHERE k=?",(k,));r=x.fetchone();return r[0] if r else d

def jwt_p(t):
    try:
        s=t.split(".")[1];s+="="*(-len(s)%4);return json.loads(base64.urlsafe_b64decode(s))
    except Exception as e:return {"err":str(e)}
def jwt_uid(t):return jwt_p(t).get("userId")
def jwt_days(t):return(jwt_p(t).get("exp",0)-time.time())/86400

def seed():
    a=0
    for t in SEED_TOKENS:
        if jwt_uid(t) and db_add(f"Account {len(db_list())+1}",t) is not None:a+=1
    log(f"seed: {a} new")

def tg_send(c,t,kb=None):
    d={"chat_id":c,"text":t,"parse_mode":"Markdown"}
    if kb:d["reply_markup"]=json.dumps(kb)
    try:requests.post(f"{TG}/sendMessage",data=d,timeout=15)
    except Exception as e:log("tg_send",e)
def tg_edit(c,m,t,kb=None):
    d={"chat_id":c,"message_id":m,"text":t,"parse_mode":"Markdown"}
    if kb:d["reply_markup"]=json.dumps(kb)
    try:requests.post(f"{TG}/editMessageText",data=d,timeout=15)
    except Exception as e:log("tg_edit",e)
def tg_ans(cb,t=None):
    d={"callback_query_id":cb}
    if t:d["text"]=t
    try:requests.post(f"{TG}/answerCallbackQuery",data=d,timeout=10)
    except Exception:pass

def hdr(t):
    return {"accept":"application/json, text/plain, */*","authorization":f"Bearer {t}","x-platform":"android","x-app-version":"81229","x-is-rooted":"false","x-is-emulator":"false","x-device-fingerprint":"dev_248f03ee566cfa70|iQOO|I2301|15","x-device-ua":"Mozilla/5.0 (Linux; Android 15; I2301 Build/AP3A.240905.015.A2; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/152.0.7977.88 Mobile Safari/537.36","content-type":"application/json","user-agent":"okhttp/4.10.0","accept-encoding":"gzip"}
def api_get(t,p):return requests.get(BASE+p,headers=hdr(t),timeout=30).json()
def api_post(t,p,b=None):return requests.post(BASE+p,headers=hdr(t),json=b or {},timeout=30).json()
def gap(s,l,N=None):
    if N:N(f"⏳ {s}s — {l}")
    e=time.time()+s
    while time.time()<e:time.sleep(min(5,max(.5,e-time.time())))
    if N:N(f"✅ {l}")
def status(t):
    j=api_get(t,"/api/superoffers/status")
    if not j.get("success"):raise RuntimeError(f"status {j}")
    return j["data"]
def iso_ms(s):
    if not s:return None
    try:return datetime.fromisoformat(s.replace("Z","+00:00")).timestamp()
    except Exception:return None

def farm_1(t,N=None):
    c=api_post(t,"/api/ballmaxxing/gem-config",{}).get("data",{}) or {}
    ms=c.get("milestones",[]);idx=c.get("ladderClaimedIdx",-1)
    if c.get("dailyEarnedToday",0)>=c.get("dailyCap",60):
        if N:N("⚠️ daily cap")
        return 0
    ni=idx+1
    if ni>=len(ms):
        if N:N("⚠️ all claimed")
        return 0
    sec,gm=ms[ni];w=sec+MARG
    if N:N(f"🎯 rung #{ni}: {sec}s → +{gm}💎")
    s=api_post(t,"/api/ballmaxxing/start",{})
    if not s.get("success"):
        if N:N(f"❌ start {s}")
        return 0
    s=s["data"];gap(w,"run",N)
    r=api_post(t,"/api/ballmaxxing/run",{"sessionId":s["sessionId"],"token":s["token"],"total":3000,"surgeBonus":0,"airBonus":500,"survivalMs":w*1000,"saves":25,"revives":0,"quit":False})
    d=r.get("data",{});aw=d.get("gemsAwarded",0)
    if N:N(f"💎 +{aw} {d.get('gemDailyTotal')}/{d.get('gemDailyCap')}")
    return aw
def farm_until(t,tg,N=None):
    z=0
    while True:
        b=status(t)["currentGemBalance"]
        if b>=tg:return b
        if N:N(f"farming bal={b} need={tg}")
        g=farm_1(t,N)
        if g==0:
            z+=1
            if z>=3:return b
            gap(5,"backoff",N)
        else:z=0

def enter(t,N=None):
    r=api_post(t,"/api/superoffers/enter",{})
    if not r.get("success"):
        if N:N(f"❌ enter {r}")
        return None
    d=r["data"]
    if N:N(f"✅ #{d['attempt_id']} cost={d['gems_cost']}")
    return d["attempt_id"]
def do_game(t,a,N=None):
    gap(G_SURV,"game",N)
    api_post(t,"/api/superoffers/game-complete",{"attempt_id":a,"source":"ballmaxxing","goals":2500,"elapsed_sec":G_SURV})
    gap(G_AFTER,"register",N)
def do_ad(t,a,N=None):
    gap(AD_W,"ad",N)
    api_post(t,"/api/superoffers/ad-complete",{"attempt_id":a})
def do_inst(t,a,s,N=None):
    p,n=INSTALL.get(s,(f"com.filler.app{s}",f"App{s}"))
    gap(I_W,f"install {n}",N)
    api_post(t,"/api/superoffers/install-detected",{"attempt_id":a,"app_package":p,"app_name":n})
    gap(U_W,"usage ≥120s",N)
    api_post(t,"/api/superoffers/verify-usage",{"attempt_id":a,"usage_minutes":2})
def do_claim(t,a,u,N=None):
    gap(C_GAP,"claim",N)
    r=api_post(t,"/api/superoffers/complete",{"attempt_id":a,"spend_id":f"SO_{a}_{u}_{int(time.time()*1000)}"})
    d=r.get("data",{})
    if N:N(f"✅ coins={d.get('coins_awarded')} bal={d.get('new_coin_balance')} cd={d.get('cooldown_hours')}h")
    return d
def run_stage(acc,N=None):
    _,n,t,u=acc
    def NN(m):
        if N:N(m)
    st=status(t);ip=st.get("inProgressAttempt")
    if ip is None:
        if not st["canEnter"]:
            cd=iso_ms(st.get("cooldownEndsAt"))
            if cd and cd>time.time():
                w=int(cd-time.time())+2;NN(f"🛏 cooldown {w}s");time.sleep(w)
            st=status(t)
            if not st["canEnter"]:NN("❌ cannot enter");return False
        if st["currentGemBalance"]<st["gemsCost"]:farm_until(t,st["gemsCost"],NN)
        a=enter(t,NN)
        if not a:return False
        state="pending"
    else:
        a=ip["id"];state=ip.get("status","pending");NN(f"↩️ resume #{a} {state}")
    if state=="pending":do_game(t,a,NN);state="game_done"
    if state in("pending","game_done"):do_ad(t,a,NN);state="ad_watched"
    s=st["attemptNumber"]
    if next((r["install"] for r in st["ladder"] if r["stage"]==s),False) and state in("pending","game_done","ad_watched"):do_inst(t,a,s,NN)
    do_claim(t,a,u,NN);return True

JOBS={}
def running(i):return JOBS.get(i,False)
def spawn(i,fn,*a):
    if running(i):return False
    JOBS[i]=True
    def w():
        try:fn(*a)
        except Exception as e:log("job",e,traceback.format_exc())
        finally:JOBS[i]=False
    threading.Thread(target=w,daemon=True).start();return True

def kb_main():
    r=[[{"text":("🟢 " if running(i) else "")+n,"callback_data":f"a:{i}"}] for i,n,u in db_list()]
    r.append([{"text":"➕ Add Token","callback_data":"add"}]);r.append([{"text":"🔄 Refresh","callback_data":"home"}])
    return {"inline_keyboard":r}
def kb_acc(i):return {"inline_keyboard":[[{"text":"📊 Status","callback_data":f"s:{i}"}],[{"text":"▶️ Run Next Stage","callback_data":f"n:{i}"}],[{"text":"🏁 Run All Stages","callback_data":f"r:{i}"}],[{"text":"💰 Farm Gems","callback_data":f"f:{i}"}],[{"text":"🗑 Remove","callback_data":f"x:{i}"}],[{"text":"◀️ Back","callback_data":"home"}]]}
def kb_rm(i):return {"inline_keyboard":[[{"text":"✅ Yes, remove","callback_data":f"y:{i}"}],[{"text":"❌ Cancel","callback_data":f"a:{i}"}]]}

def menu_text():
    a=db_list();L=[f"*OfferPlay Bot v{V}*",f"Accounts: *{len(a)}*",""]
    if not a:L.append("_No accounts._")
    else:
        for i,n,u in a:L.append(f"• *#{i}* `{u[:12]}…`{' 🟢' if running(i) else ''}")
    L.append("");L.append("_Tap an account below_");return "\n".join(L)
def acc_text(i):
    a=db_get(i)
    if not a:return "_not found_"
    _,n,t,u=a;d=jwt_days(t)
    try:
        st=status(t);s=st["attemptNumber"];g=st["currentGemBalance"];ce=st["canEnter"];cd=st.get("cooldownEndsAt") or "—"
        ip=st.get("inProgressAttempt");ipt=f"`{ip['status']}` id={ip['id']}" if ip else "—"
    except Exception:s=g="?";ce=False;cd="err";ipt="—"
    return f"*#{i} — {n}*\nuid: `{u}`\ntoken: {d:.1f}d left\nstatus: {'🟢 RUNNING' if running(i) else '⚪ idle'}\n\nstage: {s}/20\ngems: {g}\ncanEnter: {ce}\ncooldown: {cd}\ninProgress: {ipt}"

def cb(c):
    cid=c["id"];ch=c["message"]["chat"]["id"];mid=c["message"]["message_id"];d=c.get("data","")
    if d=="home":tg_ans(cid);tg_edit(ch,mid,menu_text(),kb_main())
    elif d=="add":
        tg_ans(cid);kv_set(f"aw:{ch}","add")
        tg_edit(ch,mid,"Paste your *bearer token* (`eyJ...`).\n\n/cancel to abort.",{"inline_keyboard":[[{"text":"❌ Cancel","callback_data":"home"}]]})
    elif d.startswith("a:"):i=int(d.split(":")[1]);tg_ans(cid);tg_edit(ch,mid,acc_text(i),kb_acc(i))
    elif d.startswith("s:"):i=int(d.split(":")[1]);tg_ans(cid,"…");tg_edit(ch,mid,acc_text(i),kb_acc(i))
    elif d.startswith("x:"):i=int(d.split(":")[1]);tg_ans(cid);tg_edit(ch,mid,f"Remove *#{i}*?",kb_rm(i))
    elif d.startswith("y:"):
        i=int(d.split(":")[1]);ok=db_del(i);tg_ans(cid,"removed" if ok else "nope");tg_edit(ch,mid,menu_text(),kb_main())
    elif d.startswith("n:"):i=int(d.split(":")[1]);tg_ans(cid,"starting…");go_next(ch,i)
    elif d.startswith("r:"):i=int(d.split(":")[1]);tg_ans(cid,"starting…");go_all(ch,i)
    elif d.startswith("f:"):i=int(d.split(":")[1]);tg_ans(cid,"starting…");go_farm(ch,i)
    else:tg_ans(cid)

def go_next(ch,i):
    a=db_get(i)
    if not a:tg_send(ch,"not found");return
    def N(m):tg_send(ch,f"*#{i}* {m}")
    def j():
        tg_send(ch,f"*#{i}* ▶️ next…")
        try:
            ok=run_stage(a,N);tg_send(ch,f"*#{i}* {'✅ done' if ok else '❌ failed'}",kb_acc(i))
        except Exception as e:tg_send(ch,f"*#{i}* 💥 {e}")
    if not spawn(i,j):tg_send(ch,f"*#{i}* busy")
def go_all(ch,i):
    a=db_get(i)
    if not a:tg_send(ch,"not found");return
    def N(m):tg_send(ch,f"*#{i}* {m}")
    def j():
        tg_send(ch,f"*#{i}* 🏁 running all…")
        while True:
            try:
                st=status(a[2])
                if st["attemptNumber"]>20 or st.get("weekComplete"):tg_send(ch,f"*#{i}* 🎉 week complete");return
                if not run_stage(a,N):tg_send(ch,f"*#{i}* ❌ stopping");return
                st=status(a[2]);cd=iso_ms(st.get("cooldownEndsAt"))
                if cd and cd>time.time():
                    w=int(cd-time.time())+2;N(f"🛏 {w}s");time.sleep(w)
            except Exception as e:tg_send(ch,f"*#{i}* 💥 {e}");return
    if not spawn(i,j):tg_send(ch,f"*#{i}* busy")
def go_farm(ch,i):
    a=db_get(i)
    if not a:tg_send(ch,"not found");return
    def N(m):tg_send(ch,f"*#{i}* {m}")
    def j():
        tg_send(ch,f"*#{i}* 💰 farming…")
        try:b=farm_until(a[2],999,N);tg_send(ch,f"*#{i}* bal={b}",kb_acc(i))
        except Exception as e:tg_send(ch,f"*#{i}* 💥 {e}")
    if not spawn(i,j):tg_send(ch,f"*#{i}* busy")

def msg(m):
    ch=m["chat"]["id"];t=(m.get("text") or "").strip()
    if t=="/cancel":kv_set(f"aw:{ch}","");tg_send(ch,"Cancelled",kb_main());return
    if kv_get(f"aw:{ch}")=="add":
        if not t.startswith("eyJ"):tg_send(ch,"❌ Not a JWT.\nStarts with `eyJ...`\n\nSend or /cancel.");return
        u=jwt_uid(t)
        if not u:tg_send(ch,"❌ Invalid token.");return
        n=f"Account {len(db_list())+1}";new=db_add(n,t);kv_set(f"aw:{ch}","")
        tg_send(ch,"❌ Token already added." if new is None else f"✅ *{n}* added\nuid: `{u}`",kb_main());return
    if t.startswith("/start") or t.startswith("/accounts"):tg_send(ch,menu_text(),kb_main());return
    if t.startswith("/add"):
        kv_set(f"aw:{ch}","add");tg_send(ch,"Paste your *bearer token* (`eyJ...`).\n\n/cancel to abort.",{"inline_keyboard":[[{"text":"❌ Cancel","callback_data":"home"}]]});return
    tg_send(ch,"Use /start",kb_main())

def poll():
    off=0;log("poll started")
    while True:
        try:
            d=requests.get(f"{TG}/getUpdates",params={"offset":off,"timeout":25,"allowed_updates":json.dumps(["message","callback_query"])},timeout=35).json()
            if not d.get("ok"):log("bad",d);time.sleep(3);continue
            for u in d.get("result",[]):
                off=u["update_id"]+1
                try:
                    if "callback_query" in u:cb(u["callback_query"])
                    elif "message" in u:msg(u["message"])
                except Exception as e:log("upd",e)
        except requests.exceptions.ReadTimeout:continue
        except Exception as e:log("poll err",e);time.sleep(3)

def tg_boot():
    while True:
        try:
            if CHAT_ID:tg_send(CHAT_ID,f"🚀 OfferPlay Bot v{V} online")
            poll()
        except Exception as e:log("tg_boot crashed:",e);time.sleep(10)

app=Flask(__name__)
@app.route("/")
def index():return "Active",200
@app.route("/health")
def health():return "Active",200
@app.route("/status")
def status_page():return jsonify({"ok":True,"version":V,"accounts":len(db_list()),"uptime_sec":int(time.time()-T0),"time":datetime.utcnow().isoformat()+"Z"})
@app.route("/stop")
def stop():os._exit(1)

if __name__=="__main__":
    seed()
    threading.Thread(target=tg_boot,daemon=True).start()
    app.run(host="0.0.0.0",port=PORT,threaded=True)
