import os,json,time,base64,sqlite3,threading,secrets,random,traceback,uuid
import requests
from datetime import datetime
from flask import Flask,jsonify

ACC=[
("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiJjbXVvNnNnMmhndDgxNDFpYTB3OWJoOTc3IiwiaWF0IjoxNzkwODY4ODEwLCJleHAiOjE3OTM0NjA4MTB9.y0yPgEvJumYFfVrCx0sZ1Gs38NUEXhsrLy2sA3ov7-0","25e2ce4f51201ace","Account 1"),
("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiJjbXVvNnc5MjlndnJ4NDFpYWVxOTMxcmlpIiwiaWF0IjoxNzkwODY4OTA3LCJleHAiOjE3OTM0NjA5MDd9.AjHoji0qPTDOUH4jnC17tRajWQRtkeKD8rBijPEknMg","4ab7cfe2bbb09015","Account 2"),
("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiJjbXVvNzA2bHdneTRkNDFpYW05YjBlbmR6IiwiaWF0IjoxNzkwODY5MDA1LCJleHAiOjE3OTM0NjEwMDV9.vCdy3XlTXsfiPr4CLrgPa91NCa86Ae02wo_ykv9QnFg","43c6c40ce8eb1ead","Account 3"),
("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiJjbXVvNzMwcWpnenptNDFpYTllZnZya3NzIiwiaWF0IjoxNzkwODY5MTQ2LCJleHAiOjE3OTM0NjExNDZ9.b6a6sOQRthj9TtxB9eVSxZxaiplAEgFhWLAKse2xpf0","012dcdac07908378","Account 4"),
("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiJjbXMwbWNjcWMzcDhuYmF5ZW1semVneGk2IiwiaWF0IjoxNzkwNjg4NDY5LCJleHAiOjE3OTMyODA0Njl9.tJ4inhpi1T2t9sJ7mIWxQyJphuo5ztz8rR_tkTz35o4","b519212b9bd0f528","Account 5")]

BOT="8817040407:AAHxM7D7l5Cc7yuIZvpaeS7guyIzQic9fQI"
CHAT="1827265590"
PORT=int(os.environ.get("PORT","10000"))
DBP=os.environ.get("DB_PATH","/data/accounts.db")
if not os.path.isdir(os.path.dirname(DBP)):DBP="accounts.db"
BASE="https://api.offerplay.in"
TG=f"https://api.telegram.org/bot{BOT}"
V="2.4.0"
BR,MD,AV,BUILD="iQOO","I2301","15","AP3A.240905.015.A2"
GS,GA,AW,IW,UW,CG=35,5,20,35,130,3
INST={2:("com.vedantu.app","Vedantu"),5:("com.phonepe.app","PhonePe"),
      8:("in.swiggy.android","Swiggy"),12:("com.flipkart.android","Flipkart"),
      15:("com.myntra.android","Myntra"),18:("net.one97.paytm","Paytm")}

DB=sqlite3.connect(DBP,check_same_thread=False)
LK=threading.Lock()
DB.execute("CREATE TABLE IF NOT EXISTS accounts(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,token TEXT UNIQUE,uid TEXT,hx TEXT,at TEXT)")
DB.execute("CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY,v TEXT)")
DB.commit()

def log(*a):print(f"[{datetime.utcnow():%H:%M:%S}]",*a,flush=True)
def jp(t):
    try:
        s=t.split(".")[1];s+="="*(-len(s)%4)
        return json.loads(base64.urlsafe_b64decode(s))
    except:return{}
def jid(t):return jp(t).get("userId")
def jd(t):return(jp(t).get("exp",0)-time.time())/86400
def dbadd(n,t,h):
    with LK:
        try:c=DB.execute("INSERT INTO accounts(name,token,uid,hx,at)VALUES(?,?,?,?,?)",(n,t,jid(t),h,datetime.utcnow().isoformat()));DB.commit();return c.lastrowid
        except sqlite3.IntegrityError:return None
def dbls():
    with LK:return DB.execute("SELECT id,name,uid FROM accounts ORDER BY id").fetchall()
def dbgt(i):
    with LK:return DB.execute("SELECT id,name,token,uid,hx FROM accounts WHERE id=?",(i,)).fetchone()
def dbdel(i):
    with LK:c=DB.execute("DELETE FROM accounts WHERE id=?",(i,));DB.commit();return c.rowcount>0
def kvs(k,v):
    with LK:DB.execute("INSERT OR REPLACE INTO kv VALUES(?,?)",(k,v));DB.commit()
def kvg(k,d=None):
    with LK:r=DB.execute("SELECT v FROM kv WHERE k=?",(k,)).fetchone();return r[0] if r else d
def mh():return secrets.token_hex(8)
def clean(h):
    if not h:return mh()
    h=h.strip().lower()
    if h.startswith("dev_"):h=h[4:]
    if "|" in h:h=h.split("|",1)[0]
    if len(h)!=16:return mh()
    try:int(h,16)
    except:return mh()
    return h
def ms():return int(time.time()*1000)
def ims(s):
    if not s:return None
    try:return datetime.fromisoformat(s.replace("Z","+00:00")).timestamp()
    except:return None

def UA():return f"Mozilla/5.0 (Linux; Android {AV}; {MD} Build/{BUILD}; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/152.0.7977.88 Mobile Safari/537.36"
def HF(t,h):return{"accept":"application/json, text/plain, */*","authorization":f"Bearer {t}","x-platform":"android","x-app-version":"81229","x-is-rooted":"false","x-is-emulator":"false","x-device-fingerprint":f"dev_{h}|{BR}|{MD}|{AV}","x-device-ua":UA(),"accept-encoding":"gzip","user-agent":"okhttp/4.10.0","content-type":"application/json"}
def HM(t,h):return{"authorization":f"Bearer {t}","x-device-fingerprint":f"dev_{h}|{BR}|{MD}|{AV}","accept-encoding":"gzip","user-agent":"okhttp/4.10.0","content-type":"application/json"}
def GF(t,h,p):return requests.get(BASE+p,headers=HF(t,h),timeout=30).json()
def PF(t,h,p,b):return requests.post(BASE+p,headers=HF(t,h),json=b,timeout=30).json()
def PM(t,h,p,b):return requests.post(BASE+p,headers=HM(t,h),json=b,timeout=30).json()

# ---------- New: profile / packages / history / redeem ----------
def gme(t,h):
    try:return requests.get(f"{BASE}/api/users/me",headers=HF(t,h),timeout=30).json()
    except Exception as e:return{"success":False,"message":str(e)}
def gpkg(t,h):
    try:return requests.get(f"{BASE}/api/redeem/packages",headers=HF(t,h),timeout=30).json()
    except Exception as e:return{"success":False,"message":str(e)}
def ghist(t,h,page=1,limit=10):
    try:return requests.get(f"{BASE}/api/earn/redeem/history",headers=HF(t,h),params={"page":page,"limit":limit},timeout=30).json()
    except Exception as e:return{"success":False,"message":str(e)}
def dredeem(t,h,body):
    try:return requests.post(f"{BASE}/api/redeem/request",headers=HF(t,h),json=body,timeout=60).json()
    except Exception as e:return{"success":False,"message":str(e)}

def profile_txt(i):
    a=dbgt(i)
    if not a:return"_nf_"
    _,n,t,u,h=a
    d=gme(t,h)
    if not d.get("success"):return f"*#{i} {n}*\n❌ {d.get('message') or 'fail'}"
    x=d["data"]
    return (f"*#{i} {n}*\n"
            f"name:`{x.get('name')}`\n"
            f"email:`{x.get('email')}`\n"
            f"status:{x.get('status')}\n"
            f"coins:*{x.get('coinBalance')}*\n"
            f"uid:`{u}`\n"
            f"fp:`dev_{h}|{BR}|{MD}|{AV}`")

def show_pkgs(ch,i):
    a=dbgt(i)
    if not a:return tgs(ch,"not found")
    d=gpkg(a[2],a[4])
    if not d.get("success"):return tgs(ch,f"❌ {d.get('message') or 'fail'}",kstg(i))
    pkgs=[p for p in (d.get("data") or []) if not p.get("lockedForUser")]
    pkgs.sort(key=lambda p:p.get("coinsRequired",0))
    if not pkgs:return tgs(ch,f"*#{i}* no unlocked packages",kstg(i))
    kvs(f"pk:{ch}",json.dumps([p.get("id") for p in pkgs]))
    rows=[]
    for idx,p in enumerate(pkgs):
        nm=(p.get("name") or p.get("type") or "")[:26]
        rows.append([{"text":f"{p.get('coinsRequired',0)}💰 → ₹{p.get('amountInr',0)} · {nm}",
                      "callback_data":f"rp:{i}:{idx}"}])
    rows.append([{"text":"◀️ Back","callback_data":f"a:{i}"}])
    tgs(ch,f"*#{i}* packages — tap to redeem",{"inline_keyboard":rows})

def begin_redeem(ch,i,idx):
    a=dbgt(i)
    if not a:return tgs(ch,"nf")
    try:pids=json.loads(kvg(f"pk:{ch}") or "[]")
    except:pids=[]
    if idx>=len(pids):return tgs(ch,"stale — reopen packages",kstg(i))
    d=gpkg(a[2],a[4])
    pkgs=[p for p in (d.get("data") or []) if p.get("id")==pids[idx]]
    if not pkgs:return tgs(ch,"package gone",kstg(i))
    p=pkgs[0]
    md=gme(a[2],a[4]);em=""
    if md.get("success"):em=(md["data"] or {}).get("email") or ""
    fields=[]
    for f in (p.get("customFields") or []):
        k=f.get("key")
        if not k:continue
        fd={"key":k,"label":f.get("label",k),"required":bool(f.get("required"))}
        if k=="email" and em:fd["default"]=em
        fields.append(fd)
    state={"acc":i,"pkg_id":p.get("id"),"pkg_name":p.get("name"),
           "coins":p.get("coinsRequired"),"inr":p.get("amountInr"),
           "rtype":p.get("type","GIFT_CARD"),
           "fields":fields,"values":{},"idx":0,"awaiting":bool(fields)}
    kvs(f"rd:{ch}",json.dumps(state))
    if not fields:
        return confirm_redeem(ch,state)
    nf=fields[0]
    p_=nf["label"]
    if not nf.get("required"):p_+=" (optional)"
    if nf.get("default"):p_+=f" [{nf['default']}]"
    tgs(ch,f"*{state['pkg_name']}* · {state['coins']}💰 → ₹{state['inr']}\n\n{nf['label']}",
        {"inline_keyboard":[[{"text":"❌ Cancel","callback_data":"rx"}]]})

def confirm_redeem(ch,state):
    L=[f"*Confirm redeem — #{state['acc']}*","",
       f"package: {state['pkg_name']}",
       f"coins: {state['coins']}",
       f"value: ₹{state['inr']}",""]
    for k,v in state["values"].items():
        L.append(f"`{k}`: {v}")
    tgs(ch,"\n".join(L),{"inline_keyboard":[
        [{"text":"✅ Confirm","callback_data":"rc"},{"text":"❌ Cancel","callback_data":"rx"}]
    ]})

def show_history_page(ch,i,page=1):
    a=dbgt(i)
    if not a:return tgs(ch,"nf")
    d=ghist(a[2],a[4],page=page,limit=6)
    if not d.get("success"):return tgs(ch,f"❌ {d.get('message') or 'fail'}",kstg(i))
    data=d["data"];reds=data.get("redemptions",[])
    total=data.get("total",0);pages=max(1,data.get("pages",1))
    L=[f"*#{i}* history — {page}/{pages} · total {total}",""]
    if not reds:L.append("_none_")
    for r in reds:
        st=r.get("status","")
        em="✅" if st=="completed" else ("⏳" if st in("pending","processing") else "❌")
        when=(r.get("createdAt") or "")[:10]
        L.append(f"{em} `{r.get('coinsRedeemed')}`💰 → ₹{r.get('amountInr')} · {when}")
        L.append(f"   {r.get('productName') or r.get('type')}")
        if r.get("voucherCode"):L.append(f"   code:`{r['voucherCode']}`")
        if r.get("failureReason"):L.append(f"   ❌ {r['failureReason']}")
    nav=[]
    if page>1:nav.append({"text":"◀️","callback_data":f"h:{i}:{page-1}"})
    nav.append({"text":f"{page}/{pages}","callback_data":"noop"})
    if page<pages:nav.append({"text":"▶️","callback_data":f"h:{i}:{page+1}"})
    tgs(ch,"\n".join(L),{"inline_keyboard":[nav,[{"text":"◀️ Back","callback_data":f"a:{i}"}]]})

def show_fraud(ch,i):
    a=dbgt(i)
    if not a:return tgs(ch,"nf")
    d=ghist(a[2],a[4],page=1,limit=15)
    if not d.get("success"):return tgs(ch,f"❌ {d.get('message') or 'fail'}",kstg(i))
    reds=d["data"].get("redemptions",[])
    if not reds:return tgs(ch,f"*#{i}* no redemptions yet",kstg(i))
    L=[f"*#{i}* fraud report",""]
    for r in reds:
        sc=r.get("fraudScoreSnapshot")
        if sc is None:em="⚪";sct="n/a"
        elif sc<30:em="🟢";sct=str(sc)
        elif sc<60:em="🟡";sct=str(sc)
        elif sc<80:em="🟠";sct=str(sc)
        else:em="🔴";sct=str(sc)
        when=(r.get("createdAt") or "")[:16].replace("T"," ")
        L.append(f"{em} {sct} · ₹{r.get('amountInr')} · {r.get('status')} · {when}")
        if r.get("reviewReason"):L.append(f"   🔍 {r['reviewReason']}")
        if r.get("fraudReasons"):L.append(f"   🚨 {json.dumps(r['fraudReasons'])[:110]}")
        if r.get("adminNote"):L.append(f"   📝 {r['adminNote']}")
    tgs(ch,"\n".join(L),kstg(i))

def TGs(m,d):
    try:requests.post(f"{TG}/{m}",data=d,timeout=15)
    except:pass
def tgs(c,t,kb=None):
    d={"chat_id":c,"text":t,"parse_mode":"Markdown"}
    if kb:d["reply_markup"]=json.dumps(kb)
    TGs("sendMessage",d)
def tge(c,m,t,kb=None):
    d={"chat_id":c,"message_id":m,"text":t,"parse_mode":"Markdown"}
    if kb:d["reply_markup"]=json.dumps(kb)
    TGs("editMessageText",d)
def tga(cb,t=None):
    d={"callback_query_id":cb}
    if t:d["text"]=t
    TGs("answerCallbackQuery",d)

class Stop(Exception):pass
JOB,JLK={},threading.Lock()
STP,SLK={},threading.Lock()
def ev(i):
    with SLK:
        e=STP.get(i)
        if e is None:e=threading.Event();STP[i]=e
        return e
def rst(i):ev(i).set()
def clr(i):ev(i).clear()
def ck(i):
    if ev(i).is_set():raise Stop(f"#{i}")
def run(i):
    with JLK:return JOB.get(i,False)
def sp(i,fn,*a):
    with JLK:
        if JOB.get(i,False):return False
        JOB[i]=True
    clr(i)
    def w():
        try:fn(*a)
        except Stop:pass
        except Exception as e:log("job",e,traceback.format_exc())
        finally:
            with JLK:JOB[i]=False
            clr(i)
    threading.Thread(target=w,daemon=True).start();return True
def gap(s,l,N=None,i=None):
    if N:N(f"⏳ {s}s — {l}")
    e=time.time()+s
    while time.time()<e:
        if i is not None:ck(i)
        time.sleep(min(.5,max(.05,e-time.time())))
    if i is not None:ck(i)
    if N:N(f"✅ {l}")

def st(t,h):
    j=GF(t,h,"/api/superoffers/status")
    if not j.get("success"):raise RuntimeError(f"status {j}")
    return j["data"]
def events(t,h,e):return PF(t,h,"/api/superoffers/events",{"events":e})
def enter(t,h):
    j=PM(t,h,"/api/superoffers/enter",{})
    return j.get("data") if j.get("success") else None
def game(t,h,a,go,s):return PF(t,h,"/api/superoffers/game-complete",{"attempt_id":a,"source":"ballmaxxing","goals":go,"elapsed_sec":s})
def adc(t,h,a):return PF(t,h,"/api/superoffers/ad-complete",{"attempt_id":a})
def ins(t,h,a,p,n):return PF(t,h,"/api/superoffers/install-detected",{"attempt_id":a,"app_package":p,"app_name":n})
def usg(t,h,a):return PF(t,h,"/api/superoffers/verify-usage",{"attempt_id":a,"usage_minutes":2})
def claim(t,h,a,u):return PM(t,h,"/api/superoffers/complete",{"attempt_id":a,"spend_id":f"SO_{a}_{u}_{ms()}"})
def bst(t,h):
    j=PM(t,h,"/api/ballmaxxing/start",{})
    return j.get("data") if j.get("success") else None
def brun(t,h,s,tk,to,sm):
    return PM(t,h,"/api/ballmaxxing/run",{"sessionId":s,"token":tk,"total":to,"surgeBonus":random.randint(0,200),"airBonus":random.randint(200,800),"survivalMs":sm,"saves":random.randint(10,30),"revives":0,"quit":False})
def gcf(t,h):return PF(t,h,"/api/ballmaxxing/gem-config",{}).get("data") or {}

def f1(t,h,i,N=None):
    ck(i);c=gcf(t,h);m=c.get("milestones",[]);x=c.get("ladderClaimedIdx",-1)
    if c.get("dailyEarnedToday",0)>=c.get("dailyCap",60):
        if N:N("⚠️ cap")
        return 0
    ni=x+1
    if ni>=len(m):
        if N:N("⚠️ done")
        return 0
    s,g=m[ni];w=s+5
    if N:N(f"🎯 rung {ni}: {s}s +{g}💎")
    ss=bst(t,h)
    if not ss:return 0
    gap(w,"run",N,i)
    r=brun(t,h,ss["sessionId"],ss["token"],random.randint(2000,4000),w*1000)
    return (r.get("data") or {}).get("gemsAwarded",0)
def fu(t,h,tt,i,N=None):
    z=0
    while True:
        ck(i);b=st(t,h)["currentGemBalance"]
        if b>=tt:return b
        if N:N(f"farm {b}/{tt}")
        if f1(t,h,i,N)==0:
            z+=1
            if z>=3:return b
            gap(5,"backoff",N,i)
        else:z=0

def attempt(acc,i,N=None,target=None):
    _,n,t,u,h=acc;ck(i)
    s=st(t,h);ip=s.get("inProgressAttempt");an=s["attemptNumber"]
    if target is not None:
        if ip is None and an!=target:
            if N:N(f"❌ server at stage {an}, you asked stage {target}")
            return False
        if ip is not None and an!=target:
            if N:N(f"⚠️ resuming stage {an} (server), ignoring #{target}")
        if N:N(f"🎯 target stage {target}")
    def ins_for(k):
        for r in s.get("ladder",[]):
            if r["stage"]==k:return bool(r["install"])
        return False
    fl=ins_for(an);ses=f"so_{secrets.token_hex(4)}_{secrets.token_hex(4)}"
    ns=None
    if ip is None:
        if not s["canEnter"]:
            cd=ims(s.get("cooldownEndsAt"))
            if cd and cd>time.time():
                w=int(cd-time.time())+2
                if N:N(f"🛏 cooldown {w}s — try later")
                return False
            s=st(t,h)
            if not s["canEnter"]:
                if N:N("❌ cannot enter")
                return False
        if s["currentGemBalance"]<s["gemsCost"]:fu(t,h,s["gemsCost"],i,N)
        events(t,h,[{"eventType":"cta_click","screen":"landing","target":"start","attemptNumber":an,"sessionId":ses,"occurredAt":ms()}])
        e=enter(t,h)
        if not e:
            if N:N("❌ enter fail")
            return False
        a=e["attempt_id"];an=e.get("attempt_number",an);fl=ins_for(an)
        if N:N(f"✅ #{a} cost={e.get('gems_cost')}")
        events(t,h,[{"eventType":"enter","screen":"landing","attemptId":a,"sessionId":ses,"occurredAt":ms()},
                    {"eventType":"screen_view","screen":"detail","attemptId":a,"sessionId":ses,"occurredAt":ms()},
                    {"eventType":"path_choice","screen":"detail","target":"ballmaxxing","attemptId":a,"sessionId":ses,"occurredAt":ms()}])
        state="pending"
    else:
        a=ip["id"];state=ip.get("status","pending")
        if N:N(f"↩️ resume #{a} {state}")
        events(t,h,[{"eventType":"cta_click","screen":"landing","target":"resume","attemptNumber":an,"sessionId":ses,"occurredAt":ms()},
                    {"eventType":"screen_view","screen":"detail","attemptId":a,"sessionId":ses,"occurredAt":ms()}])
        if state=="pending":
            events(t,h,[{"eventType":"path_choice","screen":"detail","target":"ballmaxxing","attemptId":a,"sessionId":ses,"occurredAt":ms()}])
    if state=="pending":
        ss=bst(t,h)
        if not ss:
            if N:N("❌ ball fail")
            return False
        gap(GS,"game",N,i)
        to=random.randint(2000,4000)
        brun(t,h,ss["sessionId"],ss["token"],to,GS*1000)
        game(t,h,a,to,GS)
        gap(GA,"register",N,i)
        state="game_done"
    if state in("pending","game_done"):
        events(t,h,[{"eventType":"ad_open","screen":"detail","target":"superOffer","attemptId":a,"sessionId":ses,"occurredAt":ms()}])
        gap(AW,"ad",N,i)
        r=adc(t,h,a);ns=(r.get("data") or {}).get("next_step")
        events(t,h,[{"eventType":"ad_earned","screen":"detail","target":"superOffer","attemptId":a,"sessionId":ses,"occurredAt":ms()}])
        state="ad_watched"
    ni=fl and (ns=="install_app" or ns is None)
    if state=="ad_watched" and ni:
        p,nm=INST.get(an,(f"com.filler.app{an}",f"App{an}"))
        gap(IW,f"install {nm}",N,i)
        ins(t,h,a,p,nm)
        gap(UW,"usage",N,i)
        usg(t,h,a)
        state="used"
    elif state=="installed":
        gap(UW,"usage",N,i)
        usg(t,h,a)
        state="used"
    gap(CG,"claim",N,i)
    r=claim(t,h,a,u);d=r.get("data") or {}
    if N:N(f"✅ coins={d.get('coins_awarded')} bal={d.get('new_coin_balance')} cd={d.get('cooldown_hours')}h")
    events(t,h,[{"eventType":"complete","screen":"detail","attemptId":a,"value":d.get("coins_awarded",0),"sessionId":ses,"occurredAt":ms()}])
    return True

def go_stage(ch,i,n):
    a=dbgt(i)
    if not a:return tgs(ch,"not found")
    def N(m):tgs(ch,f"*#{i}* {m}")
    def j():
        tgs(ch,f"*#{i}* ▶️ stage {n}…")
        try:ok=attempt(a,i,N,target=n);tgs(ch,f"*#{i}* stage {n} {'✅' if ok else '❌'}",kstg(i))
        except Stop:tgs(ch,f"*#{i}* 🛑",kstg(i))
        except Exception as e:tgs(ch,f"*#{i}* 💥 {e}")
    if not sp(i,j):tgs(ch,f"*#{i}* busy — tap STOP first")

def gfarm(ch,i):
    a=dbgt(i)
    if not a:return tgs(ch,"not found")
    def N(m):tgs(ch,f"*#{i}* {m}")
    def j():
        tgs(ch,f"*#{i}* 💰")
        try:b=fu(a[2],a[4],999,i,N);tgs(ch,f"*#{i}* bal={b}",kstg(i))
        except Stop:tgs(ch,f"*#{i}* 🛑",kstg(i))
        except Exception as e:tgs(ch,f"*#{i}* 💥 {e}")
    if not sp(i,j):tgs(ch,f"*#{i}* busy")

def km():
    r=[[{"text":("🟢 " if run(i) else "")+n,"callback_data":f"a:{i}"}] for i,n,u in dbls()]
    r+=[[{"text":"➕ Add","callback_data":"add"}],[{"text":"🔄","callback_data":"home"}]]
    return{"inline_keyboard":r}

def kstg(i):
    a=dbgt(i)
    cur=None
    try:
        if a:cur=st(a[2],a[4])["attemptNumber"]
    except:pass
    rows=[];line=[]
    for n in range(1,21):
        mark=""
        if cur is not None:
            if n<cur:mark="✅ "
            elif n==cur:mark="▶️ "
        line.append({"text":f"{mark}{n}","callback_data":f"sg:{i}:{n}"})
        if len(line)==5:rows.append(line);line=[]
    if line:rows.append(line)
    top=[]
    if run(i):top.append([{"text":"🛑 STOP","callback_data":f"st:{i}"}])
    top.append([{"text":"💰 Farm","callback_data":f"f:{i}"},{"text":"📊 Status","callback_data":f"s:{i}"}])
    top.append([{"text":"👤 Profile","callback_data":f"p:{i}"},{"text":"🎁 Redeem","callback_data":f"r:{i}"}])
    top.append([{"text":"📜 History","callback_data":f"h:{i}:1"},{"text":"🚨 Fraud","callback_data":f"fr:{i}"}])
    top.append([{"text":"🗑 Remove","callback_data":f"x:{i}"}])
    return{"inline_keyboard":top+rows+[[{"text":"◀️ Back","callback_data":"home"}]]}

def krm(i):return{"inline_keyboard":[[{"text":"✅","callback_data":f"y:{i}"}],[{"text":"❌","callback_data":f"a:{i}"}]]}

def mt():
    a=dbls();L=[f"*OP v{V}*","",f"*{len(a)}* accounts",""]
    if not a:L.append("_none_")
    else:
        for i,n,u in a:
            cur="?"
            try:
                acc=dbgt(i);cur=st(acc[2],acc[4])["attemptNumber"]
            except:pass
            L.append(f"*#{i}* `{(u or '')[:12]}…` stage {cur}/20{' 🟢' if run(i) else ''}")
    return"\n".join(L)

def atx(i):
    a=dbgt(i)
    if not a:return"_nf_"
    _,n,t,u,h=a;d=jd(t)
    try:
        s=st(t,h);sg=s["attemptNumber"];g=s["currentGemBalance"];ce=s["canEnter"]
        cd=s.get("cooldownEndsAt") or "—";ip=s.get("inProgressAttempt")
        ipt=f"`{ip['status']}` id={ip['id']}" if ip else "—"
    except:sg=g="?";ce=False;cd="err";ipt="—"
    return(f"*#{i} {n}*\nuid:`{u}`\nfp:`dev_{h}|{BR}|{MD}|{AV}`\ntok:{d:.1f}d\nst:{'🟢' if run(i) else '⚪'}\nstage:{sg}/20\ngems:{g}\nenter:{ce}\ncd:{cd}\nip:{ipt}")

def do_rc(ci,ch,mi):
    rd=kvg(f"rd:{ch}")
    if not rd:return tga(ci,"no pending"),tge(ch,mi,"no pending")
    try:state=json.loads(rd)
    except:return tga(ci,"bad state")
    a=dbgt(state["acc"])
    if not a:return tga(ci,"nf"),tge(ch,mi,"nf")
    tga(ci,"sending…")
    body={"type":state["rtype"],"coinsToRedeem":state["coins"],
          "packageId":state["pkg_id"],"customFieldValues":state["values"],
          "idempotencyKey":str(uuid.uuid4())}
    r=dredeem(a[2],a[4],body)
    if r.get("success"):
        d2=r.get("data") or {}
        kvs(f"rd:{ch}","")
        L=["✅ *redeemed*","",
           f"status: {d2.get('status')}",
           f"coins: {d2.get('coinsRedeemed')}",
           f"₹: {d2.get('amountInr')}"]
        if d2.get("voucherCode"):L.append(f"code: `{d2['voucherCode']}`")
        if d2.get("voucherPin"):L.append(f"pin: `{d2['voucherPin']}`")
        if d2.get("validity"):L.append(f"valid: {d2['validity']}")
        if d2.get("redemptionId"):L.append(f"id: `{d2['redemptionId']}`")
        tge(ch,mi,"\n".join(L),kstg(state["acc"]))
    else:
        msg=r.get("message") or r.get("error") or "fail"
        tge(ch,mi,f"❌ {msg}",kstg(state["acc"]))

def cb(c):
    ci=c["id"];ch=c["message"]["chat"]["id"];mi=c["message"]["message_id"];d=c.get("data","")
    if d=="home":tga(ci);tge(ch,mi,mt(),km())
    elif d=="noop":tga(ci)
    elif d=="add":tga(ci);kvs(f"aw:{ch}","add");tge(ch,mi,"Paste bearer (`eyJ...`).\n/cancel",{"inline_keyboard":[[{"text":"❌","callback_data":"home"}]]})
    elif d.startswith("a:"):i=int(d[2:]);tga(ci);tge(ch,mi,atx(i),kstg(i))
    elif d.startswith("s:"):i=int(d[2:]);tga(ci,"…");tge(ch,mi,atx(i),kstg(i))
    elif d.startswith("st:"):
        i=int(d[3:])
        if run(i):rst(i);tga(ci,"🛑 stopping")
        else:tga(ci,"idle")
        time.sleep(.4);tge(ch,mi,atx(i),kstg(i))
    elif d.startswith("x:"):i=int(d[2:]);tga(ci);tge(ch,mi,f"Remove #{i}?",krm(i))
    elif d.startswith("y:"):
        i=int(d[2:])
        if run(i):rst(i)
        tga(ci,"rm" if dbdel(i) else "no");tge(ch,mi,mt(),km())
    elif d.startswith("sg:"):
        _,si,sn=d.split(":")
        i=int(si);n=int(sn)
        tga(ci,f"stage {n}")
        go_stage(ch,i,n)
    elif d.startswith("f:"):i=int(d[2:]);tga(ci,"…");gfarm(ch,i)
    # ---- new ----
    elif d.startswith("p:"):i=int(d[2:]);tga(ci,"…");tge(ch,mi,profile_txt(i),kstg(i))
    elif d.startswith("r:"):i=int(d[2:]);tga(ci,"…");show_pkgs(ch,i)
    elif d.startswith("rp:"):
        _,si,pi=d.split(":")
        tga(ci,"…");begin_redeem(ch,int(si),int(pi))
    elif d=="rc":do_rc(ci,ch,mi)
    elif d=="rx":kvs(f"rd:{ch}","");tga(ci,"cancel");tge(ch,mi,"❌ Redeem cancelled",km())
    elif d.startswith("h:"):
        _,si,pg=d.split(":")
        tga(ci);show_history_page(ch,int(si),int(pg))
    elif d.startswith("fr:"):i=int(d[3:]);tga(ci,"…");show_fraud(ch,i)
    else:tga(ci)

def msg(m):
    ch=m["chat"]["id"];t=(m.get("text") or "").strip()

    # ---- redeem field input ----
    rd=kvg(f"rd:{ch}")
    if rd:
        try:state=json.loads(rd)
        except:state=None
        if state and state.get("awaiting"):
            if t=="/cancel":
                kvs(f"rd:{ch}","")
                return tgs(ch,"❌ redeem cancelled",kstg(state["acc"]))
            f=state["fields"][state["idx"]]
            val=t
            if not val and f.get("default"):val=f["default"]
            if not val and f.get("required"):
                return tgs(ch,f"*{f['label']}* is required.")
            state["values"][f["key"]]=val
            state["idx"]+=1
            if state["idx"]>=len(state["fields"]):
                state["awaiting"]=False
                kvs(f"rd:{ch}",json.dumps(state))
                return confirm_redeem(ch,state)
            kvs(f"rd:{ch}",json.dumps(state))
            nf=state["fields"][state["idx"]]
            p_=nf["label"]
            if not nf.get("required"):p_+=" (optional)"
            if nf.get("default"):p_+=f" [{nf['default']}]"
            return tgs(ch,f"*{state['pkg_name']}*\n\n{p_}",
                       {"inline_keyboard":[[{"text":"❌ Cancel","callback_data":"rx"}]]})

    if t=="/cancel":kvs(f"aw:{ch}","");return tgs(ch,"Cancel",km())
    if t.startswith("/stop"):
        p=t.split()
        if len(p)==2 and p[1].isdigit():
            i=int(p[1])
            if run(i):rst(i);return tgs(ch,f"🛑 #{i}",kstg(i))
            return tgs(ch,f"#{i} idle")
        nn=0
        for i,_,_ in dbls():
            if run(i):rst(i);nn+=1
        return tgs(ch,f"🛑 {nn}",km())
    if kvg(f"aw:{ch}")=="add":
        if not t.startswith("eyJ"):return tgs(ch,"❌ not JWT")
        u=jid(t)
        if not u:return tgs(ch,"❌ bad")
        h=mh();nm=f"Account {len(dbls())+1}";new=dbadd(nm,t,h);kvs(f"aw:{ch}","")
        if new is None:return tgs(ch,"❌ dup",km())
        return tgs(ch,f"✅ {nm}\nuid:`{u}`\nfp:`dev_{h}|{BR}|{MD}|{AV}`",km())
    if t.startswith("/start") or t.startswith("/accounts"):return tgs(ch,mt(),km())
    if t.startswith("/add"):kvs(f"aw:{ch}","add");return tgs(ch,"Paste bearer (`eyJ...`).\n/cancel",{"inline_keyboard":[[{"text":"❌","callback_data":"home"}]]})
    tgs(ch,"/start",km())

def poll():
    o=0;log("poll")
    while True:
        try:
            d=requests.get(f"{TG}/getUpdates",params={"offset":o,"timeout":25,"allowed_updates":json.dumps(["message","callback_query"])},timeout=35).json()
            if not d.get("ok"):log("bad",d);time.sleep(3);continue
            for u in d.get("result",[]):
                o=u["update_id"]+1
                try:
                    if "callback_query" in u:cb(u["callback_query"])
                    elif "message" in u:msg(u["message"])
                except Exception as e:log("u",e)
        except requests.exceptions.ReadTimeout:continue
        except Exception as e:log("p",e);time.sleep(3)

def boot():
    while True:
        try:
            if CHAT:tgs(CHAT,f"🚀 OP v{V}")
            poll()
        except Exception as e:log("boot",e);time.sleep(10)

def seed():
    a=0
    for r in ACC:
        t=r[0].strip();h=r[1] if len(r)>1 else "";n=r[2] if len(r)>2 and r[2] else f"Account {len(dbls())+1}"
        if not t.startswith("eyJ"):continue
        if not jid(t):continue
        if dbadd(n,t,clean(h)) is not None:a+=1
    log(f"seed {a}")

app=Flask(__name__)
@app.route("/")
def idx():return"Active",200
@app.route("/health")
def hlth():return"Active",200
@app.route("/status")
def statpage():return jsonify({"ok":True,"v":V,"n":len(dbls()),"run":[i for i,_,_ in dbls() if run(i)]})
@app.route("/stop")
def stp():os._exit(1)

if __name__=="__main__":
    seed()
    threading.Thread(target=boot,daemon=True).start()
    app.run(host="0.0.0.0",port=PORT,threaded=True)