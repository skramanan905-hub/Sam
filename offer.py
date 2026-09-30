import os,json,time,base64,sqlite3,threading,traceback,requests,secrets,random
from datetime import datetime
from flask import Flask,jsonify

BOT="8817040407:AAHxM7D7l5Cc7yuIZvpaeS7guyIzQic9fQI"
CHAT="1827265590"
ACC=[
("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiJjbXVtcTRseXVvaTlvNDFpYXphdWF2cWFkIiwiaWF0IjoxNzkwNjg5MjIxLCJleHAiOjE3OTMyODEyMjF9.loVti8fe5sTWhwp4GXu3u55MDVJxPRkQk34zvzNxhgA","62ad069c01631b29"),
("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiJjbXVtcmNyMzlwZDN1NDFpYTd3OTUwMnc4IiwiaWF0IjoxNzkwNjkxMzA2LCJleHAiOjE3OTMyODMzMDZ9.JXn83z2WEBoBCT9HOzUPfs7UusyXOPkYsTmEmrR5LRk","20f4ff3d112880f4"),
("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiJjbXVtcmljYm5waGJxNDFpYTR5aWs4NWxrIiwiaWF0IjoxNzkwNjkxNTQxLCJleHAiOjE3OTMyODM1NDF9.RgZTeyQrZZkKZcGJWPQ9ZmRci5--68n9-JJKYnhemaQ","1913f4565d43fe8c"),
("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiJjbXVtcmx5dWVwamk0NDFpYWc1bmQydmc0IiwiaWF0IjoxNzkwNjkxNzEwLCJleHAiOjE3OTMyODM3MTB9._43tBDZ_whHbTaS1bRn0hAthSj1x4NQzqz2Ig8ITFM4","3dd805f9a7d385d3"),
("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiJjbXVtcnFrb2VwbWJxNDFpYXk1cjU2MXVqIiwiaWF0IjoxNzkwNjkxOTI3LCJleHAiOjE3OTMyODM5Mjd9.W7UbwRrKIgfJgXrV1wB-HZsHESm50DKFpeR0CqTABqs","37e6fa13e40e026b")]

BR,MD,AV="iQOO","I2301","15"
BASE="https://api.offerplay.in"
TG=f"https://api.telegram.org/bot{BOT}"
V="1.0.23"
PORT=int(os.environ.get("PORT","10000"))
DBP=os.environ.get("DB_PATH","/data/accounts.db")
if not os.path.isdir(os.path.dirname(DBP)):DBP="accounts.db"
GS,GA,AW,IW,UW,CG,MG=35,5,20,30,125,3,5
INST={2:("org.coursera.android","Coursera"),5:("com.bigbasket.mobileapp","BigBasket"),8:("com.yubi.android.my.yubi.invest","Aspero"),12:("com.adobe.spark.post","Adobe Express"),15:("com.ril.shein","SHEIN")}
def log(*a):print(f"[{datetime.utcnow():%H:%M:%S}]",*a,flush=True)

# DB
DB=sqlite3.connect(DBP,check_same_thread=False);LK=threading.Lock()
DB.execute("CREATE TABLE IF NOT EXISTS accounts(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,token TEXT UNIQUE,uid TEXT,dev TEXT,at TEXT)")
DB.execute("CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY,v TEXT)");DB.commit()
def jp(t):
    try:
        s=t.split(".")[1];s+="="*(-len(s)%4);return json.loads(base64.urlsafe_b64decode(s))
    except:return{}
def jid(t):return jp(t).get("userId")
def jdays(t):return(jp(t).get("exp",0)-time.time())/86400
def dbadd(n,t,d):
    with LK:
        try:c=DB.execute("INSERT INTO accounts(name,token,uid,dev,at)VALUES(?,?,?,?,?)",(n,t,jid(t),d,datetime.utcnow().isoformat()));DB.commit();return c.lastrowid
        except sqlite3.IntegrityError:return None
def dblist():
    with LK:return DB.execute("SELECT id,name,uid FROM accounts ORDER BY id").fetchall()
def dbget(i):
    with LK:return DB.execute("SELECT id,name,token,uid,dev FROM accounts WHERE id=?",(i,)).fetchone()
def dbdel(i):
    with LK:c=DB.execute("DELETE FROM accounts WHERE id=?",(i,));DB.commit();return c.rowcount>0
def kvs(k,v):
    with LK:DB.execute("INSERT OR REPLACE INTO kv VALUES(?,?)",(k,v));DB.commit()
def kvg(k,d=None):
    with LK:r=DB.execute("SELECT v FROM kv WHERE k=?",(k,)).fetchone();return r[0] if r else d
def mkdev():return f"{secrets.token_hex(8)}|{BR}|{MD}|{AV}"
def pdev(d):
    p=(d or "").split("|")
    if len(p)!=4 or len(p[0])<8:raise ValueError(f"bad dev:{d!r}")
    return p

# TG
def _tg(m,d):
    try:requests.post(f"{TG}/{m}",data=d,timeout=15)
    except Exception as e:log(m,e)
def tgs(c,t,kb=None):
    d={"chat_id":c,"text":t,"parse_mode":"Markdown"}
    if kb:d["reply_markup"]=json.dumps(kb)
    _tg("sendMessage",d)
def tge(c,m,t,kb=None):
    d={"chat_id":c,"message_id":m,"text":t,"parse_mode":"Markdown"}
    if kb:d["reply_markup"]=json.dumps(kb)
    _tg("editMessageText",d)
def tga(cb,t=None):
    d={"callback_query_id":cb}
    if t:d["text"]=t
    _tg("answerCallbackQuery",d)

# API
def hdr(t,d):
    h,br,md,ver=pdev(d)
    return {"accept":"application/json, text/plain, */*","authorization":f"Bearer {t}","x-platform":"android","x-app-version":"81229","x-is-rooted":"false","x-is-emulator":"false","x-device-fingerprint":f"dev_{h}|{br}|{md}|{ver}","x-device-ua":f"Mozilla/5.0 (Linux; Android {ver}; {md} Build/AP3A.240905.015.A2; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/152.0.7977.88 Mobile Safari/537.36","content-type":"application/json","user-agent":"okhttp/4.10.0","accept-encoding":"gzip"}
def aget(t,p,d):
    r=requests.get(BASE+p,headers=hdr(t,d),timeout=30);r.raise_for_status();return r.json()
def apost(t,p,b,d):
    r=requests.post(BASE+p,headers=hdr(t,d),json=b or {},timeout=30);r.raise_for_status();return r.json()

# STOP
class Stopped(Exception):pass
JOB,JLK={},threading.Lock()
STP,SLK={},threading.Lock()
def _ev(i):
    with SLK:
        e=STP.get(i)
        if e is None:e=threading.Event();STP[i]=e
        return e
def reqstop(i):_ev(i).set()
def clrstop(i):_ev(i).clear()
def ck(i):
    if _ev(i).is_set():raise Stopped(f"#{i} stopped")
def run(i):
    with JLK:return JOB.get(i,False)
def spawn(i,fn,*a):
    with JLK:
        if JOB.get(i,False):return False
        JOB[i]=True
    clrstop(i)
    def w():
        try:fn(*a)
        except Stopped as e:log("stopped",e);tgs(CHAT,f"🛑 *{e}*")
        except Exception as e:log("job",e,traceback.format_exc())
        finally:
            with JLK:JOB[i]=False
            clrstop(i)
    threading.Thread(target=w,daemon=True).start();return True

# WAIT (exact seconds + stop check)
def gap(s,l,N=None,i=None):
    if N:N(f"⏳ {s}s — {l}")
    end=time.time()+s
    while time.time()<end:
        if i is not None:ck(i)
        time.sleep(min(.5,max(.05,end-time.time())))
    if i is not None:ck(i)
    if N:N(f"✅ {l}")
def stat(t,d):
    j=aget(t,"/api/superoffers/status",d)
    if not j.get("success"):raise RuntimeError(f"status {j}")
    return j["data"]
def ims(s):
    if not s:return None
    try:return datetime.fromisoformat(s.replace("Z","+00:00")).timestamp()
    except:return None

# FARM
def farm1(t,d,i,N=None):
    ck(i)
    c=apost(t,"/api/ballmaxxing/gem-config",{},d).get("data",{}) or {}
    ms,idx=c.get("milestones",[]),c.get("ladderClaimedIdx",-1)
    if c.get("dailyEarnedToday",0)>=c.get("dailyCap",60):
        if N:N("⚠️ daily cap")
        return 0
    ni=idx+1
    if ni>=len(ms):
        if N:N("⚠️ all claimed")
        return 0
    sec,gm=ms[ni];w=sec+MG
    if N:N(f"🎯 rung #{ni}: {sec}s → +{gm}💎")
    s=apost(t,"/api/ballmaxxing/start",{},d)
    if not s.get("success"):
        if N:N(f"❌ start {s}")
        return 0
    s=s["data"];gap(w,"run",N,i)
    r=apost(t,"/api/ballmaxxing/run",{"sessionId":s["sessionId"],"token":s["token"],"total":random.randint(2000,4500),"surgeBonus":random.randint(0,400),"airBonus":random.randint(300,800),"survivalMs":w*1000,"saves":random.randint(15,35),"revives":0,"quit":False},d)
    dd=r.get("data",{});aw=dd.get("gemsAwarded",0)
    if N:N(f"💎 +{aw} {dd.get('gemDailyTotal')}/{dd.get('gemDailyCap')}")
    return aw
def farmt(t,tg,d,i,N=None):
    z=0
    while True:
        ck(i)
        b=stat(t,d)["currentGemBalance"]
        if b>=tg:return b
        if N:N(f"farming bal={b} need={tg}")
        g=farm1(t,d,i,N)
        if g==0:
            z+=1
            if z>=3:return b
            gap(5,"backoff",N,i)
        else:z=0

# STAGE
def ent(t,d,N=None):
    r=apost(t,"/api/superoffers/enter",{},d)
    if not r.get("success"):
        if N:N(f"❌ enter {r}")
        return None
    dd=r["data"]
    if N:N(f"✅ #{dd['attempt_id']} cost={dd['gems_cost']}")
    return dd["attempt_id"]
def dgame(t,a,d,i,N=None):
    gap(GS,"game",N,i)
    apost(t,"/api/superoffers/game-complete",{"attempt_id":a,"source":"ballmaxxing","goals":random.randint(1800,3500),"elapsed_sec":GS},d)
    gap(GA,"register",N,i)
def dad(t,a,d,i,N=None):
    gap(AW,"ad",N,i)
    apost(t,"/api/superoffers/ad-complete",{"attempt_id":a},d)
def dinst(t,a,s,d,i,N=None):
    p,n=INST.get(s,(f"com.filler.app{s}",f"App{s}"))
    gap(IW,f"install {n}",N,i)
    apost(t,"/api/superoffers/install-detected",{"attempt_id":a,"app_package":p,"app_name":n},d)
    gap(UW,"usage ≥120s",N,i)
    apost(t,"/api/superoffers/verify-usage",{"attempt_id":a,"usage_minutes":2},d)
def dclaim(t,a,u,d,i,N=None):
    gap(CG,"claim",N,i)
    r=apost(t,"/api/superoffers/complete",{"attempt_id":a,"spend_id":f"SO_{a}_{u}_{int(time.time()*1000)}"},d)
    dd=r.get("data",{})
    if N:N(f"✅ coins={dd.get('coins_awarded')} bal={dd.get('new_coin_balance')} cd={dd.get('cooldown_hours')}h")
    return dd
def stage(acc,i,N=None):
    _,n,t,u,d=acc
    def NN(m):
        if N:N(m)
    ck(i)
    st=stat(t,d);ip=st.get("inProgressAttempt")
    if ip is None:
        if not st["canEnter"]:
            cd=ims(st.get("cooldownEndsAt"))
            if cd and cd>time.time():
                w=int(cd-time.time())+2;NN(f"🛏 cooldown {w}s")
                end=time.time()+w
                while time.time()<end:
                    ck(i);time.sleep(min(1,max(.1,end-time.time())))
            st=stat(t,d)
            if not st["canEnter"]:NN("❌ cannot enter");return False
        if st["currentGemBalance"]<st["gemsCost"]:farmt(t,st["gemsCost"],d,i,NN)
        a=ent(t,d,NN)
        if not a:return False
        state="pending"
    else:
        a=ip["id"];state=ip.get("status","pending");NN(f"↩️ resume #{a} {state}")
    if state=="pending":dgame(t,a,d,i,NN);state="game_done"
    if state in("pending","game_done"):dad(t,a,d,i,NN);state="ad_watched"
    s=st["attemptNumber"]
    ni=next((r["install"] for r in st["ladder"] if r["stage"]==s),False)
    if ni and state in("pending","game_done","ad_watched"):dinst(t,a,s,d,i,NN)
    elif ni and state=="installed":
        gap(UW,"usage ≥120s",NN,i)
        apost(t,"/api/superoffers/verify-usage",{"attempt_id":a,"usage_minutes":2},d)
    dclaim(t,a,u,d,i,NN)
    return True

# KB
def kmain():
    r=[[{"text":("🟢 " if run(i) else "")+n,"callback_data":f"a:{i}"}] for i,n,u in dblist()]
    r+=[[{"text":"➕ Add Token","callback_data":"add"}],[{"text":"🔄 Refresh","callback_data":"home"}]]
    return {"inline_keyboard":r}
def kacc(i):
    r=[]
    if run(i):r.append([{"text":"🛑 STOP NOW","callback_data":f"st:{i}"}])
    r+=[[{"text":"📊 Status","callback_data":f"s:{i}"}],[{"text":"▶️ Run Next","callback_data":f"n:{i}"}],[{"text":"🏁 Run All","callback_data":f"r:{i}"}],[{"text":"💰 Farm Gems","callback_data":f"f:{i}"}],[{"text":"🗑 Remove","callback_data":f"x:{i}"}],[{"text":"◀️ Back","callback_data":"home"}]]
    return {"inline_keyboard":r}
def krm(i):return{"inline_keyboard":[[{"text":"✅ Yes","callback_data":f"y:{i}"}],[{"text":"❌ Cancel","callback_data":f"a:{i}"}]]}

# TEXT
def mtext():
    a=dblist();L=[f"*OfferPlay v{V}*",f"Accounts:*{len(a)}*",""]
    if not a:L.append("_No accounts._")
    else:
        for i,n,u in a:L.append(f"• *#{i}* `{u[:12]}…`{' 🟢' if run(i) else ''}")
    return"\n".join(L)
def atext(i):
    a=dbget(i)
    if not a:return"_not found_"
    _,n,t,u,d=a;dd=jdays(t)
    try:
        st=stat(t,d);s,g,ce=st["attemptNumber"],st["currentGemBalance"],st["canEnter"]
        cd=st.get("cooldownEndsAt") or "—";ip=st.get("inProgressAttempt")
        ipt=f"`{ip['status']}` id={ip['id']}" if ip else "—"
    except:s=g="?";ce=False;cd="err";ipt="—"
    return(f"*#{i} — {n}*\nuid:`{u}`\ndev:`{d}`\ntoken:{dd:.1f}d\nstatus:{'🟢 RUNNING' if run(i) else '⚪ idle'}\nstage:{s}/20\ngems:{g}\ncanEnter:{ce}\ncooldown:{cd}\ninProgress:{ipt}")

# JOBS
def gnext(ch,i):
    a=dbget(i)
    if not a:return tgs(ch,"not found")
    def N(m):tgs(ch,f"*#{i}* {m}")
    def j():
        tgs(ch,f"*#{i}* ▶️ next…")
        try:ok=stage(a,i,N);tgs(ch,f"*#{i}* {'✅ done' if ok else '❌ failed'}",kacc(i))
        except Stopped:tgs(ch,f"*#{i}* 🛑 stopped",kacc(i))
        except Exception as e:tgs(ch,f"*#{i}* 💥 {e}")
    if not spawn(i,j):tgs(ch,f"*#{i}* busy")
def gall(ch,i):
    a=dbget(i)
    if not a:return tgs(ch,"not found")
    def N(m):tgs(ch,f"*#{i}* {m}")
    def j():
        tgs(ch,f"*#{i}* 🏁 running all…")
        while True:
            try:
                ck(i);st=stat(a[2],a[4])
                if st["attemptNumber"]>20 or st.get("weekComplete"):tgs(ch,f"*#{i}* 🎉 week done");return
                if not stage(a,i,N):tgs(ch,f"*#{i}* ❌ stop");return
                cd=ims(stat(a[2],a[4]).get("cooldownEndsAt"))
                if cd and cd>time.time():
                    w=int(cd-time.time())+2;N(f"🛏 {w}s")
                    end=time.time()+w
                    while time.time()<end:ck(i);time.sleep(min(1,max(.1,end-time.time())))
            except Stopped:tgs(ch,f"*#{i}* 🛑 stopped");return
            except Exception as e:tgs(ch,f"*#{i}* 💥 {e}");return
    if not spawn(i,j):tgs(ch,f"*#{i}* busy")
def gfarm(ch,i):
    a=dbget(i)
    if not a:return tgs(ch,"not found")
    def N(m):tgs(ch,f"*#{i}* {m}")
    def j():
        tgs(ch,f"*#{i}* 💰 farming…")
        try:b=farmt(a[2],999,a[4],i,N);tgs(ch,f"*#{i}* bal={b}",kacc(i))
        except Stopped:tgs(ch,f"*#{i}* 🛑 stopped",kacc(i))
        except Exception as e:tgs(ch,f"*#{i}* 💥 {e}")
    if not spawn(i,j):tgs(ch,f"*#{i}* busy")

# CB
def cb(c):
    cid,ch,mid,d=c["id"],c["message"]["chat"]["id"],c["message"]["message_id"],c.get("data","")
    if d=="home":tga(cid);tge(ch,mid,mtext(),kmain())
    elif d=="add":tga(cid);kvs(f"aw:{ch}","add");tge(ch,mid,"Paste *bearer token* (`eyJ...`).\n\n/cancel to abort.",{"inline_keyboard":[[{"text":"❌ Cancel","callback_data":"home"}]]})
    elif d.startswith("a:"):i=int(d[2:]);tga(cid);tge(ch,mid,atext(i),kacc(i))
    elif d.startswith("s:"):i=int(d[2:]);tga(cid,"…");tge(ch,mid,atext(i),kacc(i))
    elif d.startswith("st:"):
        i=int(d[3:])
        if run(i):reqstop(i);tga(cid,"🛑 stopping…")
        else:tga(cid,"not running")
        time.sleep(.5);tge(ch,mid,atext(i),kacc(i))
    elif d.startswith("x:"):i=int(d[2:]);tga(cid);tge(ch,mid,f"Remove *#{i}*?",krm(i))
    elif d.startswith("y:"):
        i=int(d[2:])
        if run(i):reqstop(i)
        tga(cid,"removed" if dbdel(i) else "nope");tge(ch,mid,mtext(),kmain())
    elif d.startswith("n:"):i=int(d[2:]);tga(cid,"starting…");gnext(ch,i)
    elif d.startswith("r:"):i=int(d[2:]);tga(cid,"starting…");gall(ch,i)
    elif d.startswith("f:"):i=int(d[2:]);tga(cid,"starting…");gfarm(ch,i)
    else:tga(cid)

# MSG
def msg(m):
    ch,t=m["chat"]["id"],(m.get("text") or "").strip()
    if t=="/cancel":kvs(f"aw:{ch}","");return tgs(ch,"Cancelled",kmain())
    if t.startswith("/stop"):
        p=t.split()
        if len(p)==2 and p[1].isdigit():
            i=int(p[1])
            if run(i):reqstop(i);return tgs(ch,f"🛑 stopping #{i}…",kacc(i))
            return tgs(ch,f"#{i} not running")
        n=0
        for i,_,_ in dblist():
            if run(i):reqstop(i);n+=1
        return tgs(ch,f"🛑 stopping {n}…",kmain())
    if kvg(f"aw:{ch}")=="add":
        if not t.startswith("eyJ"):return tgs(ch,"❌ Not a JWT.\n`eyJ...`\n\n/cancel to abort.")
        u=jid(t)
        if not u:return tgs(ch,"❌ Invalid token.")
        dd=mkdev();n=f"Account {len(dblist())+1}";new=dbadd(n,t,dd);kvs(f"aw:{ch}","")
        return tgs(ch,"❌ Token already added." if new is None else f"✅ *{n}* added\nuid:`{u}`\ndev:`{dd}`",kmain())
    if t.startswith("/start") or t.startswith("/accounts"):return tgs(ch,mtext(),kmain())
    if t.startswith("/add"):kvs(f"aw:{ch}","add");return tgs(ch,"Paste *bearer token* (`eyJ...`).\n\n/cancel to abort.",{"inline_keyboard":[[{"text":"❌ Cancel","callback_data":"home"}]]})
    tgs(ch,"Use /start",kmain())

# POLL
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
def boot():
    while True:
        try:
            if CHAT:tgs(CHAT,f"🚀 OfferPlay Bot v{V} online")
            poll()
        except Exception as e:log("boot crash:",e);time.sleep(10)

# SEED
def seed():
    a=0
    for tok,hx in ACC:
        d=f"{hx}|{BR}|{MD}|{AV}"
        try:pdev(d)
        except ValueError as e:log("skip",e);continue
        if jid(tok) and dbadd(f"Account {len(dblist())+1}",tok,d) is not None:a+=1
    log(f"seed: {a}/{len(ACC)}")

app=Flask(__name__)
@app.route("/")
def idx():return"Active",200
@app.route("/health")
def hl():return"Active",200
@app.route("/status")
def stp():return jsonify({"ok":True,"version":V,"accounts":len(dblist()),"running":[i for i,_,_ in dblist() if run(i)]})
@app.route("/stop")
def st():os._exit(1)

if __name__=="__main__":
    seed()
    threading.Thread(target=boot,daemon=True).start()
    app.run(host="0.0.0.0",port=PORT,threaded=True)
