import os, re, json, time, requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app)

API = "https://api.pixai.art/graphql"
R2  = "https://api.pixai.art/v2"

# Verified Apollo Hashes (2026)
H = {
    "GEN": "7662bf96848c0cd1e03cafc5a6b61785481a55a1c92faec3a248da9195bf9d25",
    "POLL": "2526f64c73c59fcfeff938b0f4a8b3b610f2294bc6eb6b6b281aa671ac81a08e",
    "SEARCH": "b7a2d663bc0381dd6eb26f8c68f702cb928bea720982f6f5553ea1629a8e871d",
    "META": "5eb358cf87e145dba1615381573d015938c36655c2461f2b6d8f8bd0f0ba6826", # Fixed Live Hash
    "META_V2": "48261caf4d9d4a3f3c44c1eb001429824dfa36f7b91edb113fb7468eb53947d0",
    "CRE": "9356b42a4ff6e987347a1f1ee3de7aba4bd103b1cdbfbbc4c5c5fcf52767ad66",
    "ROLL": "f0778d88963cc4e40749a8ecd9d510808b4a14cd63fac498e7763e6d5d780e5e",
    "UPLOAD": "dd71971acde11807d01862ff1a94657479f7e833af75eac850aa2de0a14fa1fa",
    "18PLUS": "fb22173aa2a43ff08be4221a17094a1445cb212e1b1970a1cee8c37e98d38304",
    "LIST": "cc067203ddd0846c19d9e247d837c32da498247ec252fe30828434f2f136f53d",
    "ART_LIST": "4333322848527d13057adfc604ae92e3153198e7f3c42fb87ff7de91fd701f24",
    "ART_DETAIL": "247baf1bd53d4e2f370a0704eac1b980c6598b657a0a46bbbbf59d9b9350d609"
}

def get_h(t, u3t=None):
    hd = {
        "Authorization": f"Bearer {str(t or '').replace('Bearer ', '').strip()}",
        "Content-Type": "application/json",
        "x-browser-id": "08df9bc9358ad97ebfe0ac86284587e5",
        "User-Agent": "Mozilla/5.0 (Linux; Android 15; I2301 Build/AP3A.240905.015.A2) AppleWebKit/537.36 Chrome/154.0.8037.107 Mobile Safari/537.36",
        "Origin": "https://pixai.art", "Referer": "https://pixai.art/",
        "Accept": "application/graphql-response+json,application/json;q=0.9"
    }
    if u3t: hd["x-u3t"] = u3t
    return hd

def sj(r):
    try: return r.json()
    except: return {"_raw_text": r.text[:3000], "_status": r.status_code}

def clean_txt(t): return re.sub(r'[_*`\[\]()~>#+\-={}|.!]', '', str(t or '')) if t != "null" else ""
def fmt_time(ts):
    try: return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ").strftime("%b %d, %Y %I:%M %p")
    except: return ts or ""
def fmt_num(n):
    try:
        n = int(n or 0)
        return f"{n/1e6:.2f}m" if n >= 1e6 else (f"{n/1e3:.2f}k" if n >= 1e3 else str(n))
    except: return "0"

def pick_thumb(m):
    if not m: return "", ""
    t, p = "", ""
    for u in (m.get("urls") or []):
        v = u.get("variant")
        if v == "STILL_THUMBNAIL": t = u.get("url", "")
        elif v == "THUMBNAIL" and not t: t = u.get("url", "")
        elif v == "PUBLIC": p = u.get("url", "")
    return t or m.get("thumbnailUrl", "") or p, p or m.get("publicUrl", "") or t

def apq(op, vars_dict, hash_key, token, u3t=None):
    p = {"operation": op, "operationName": op, "variables": json.dumps(vars_dict, separators=(',', ':')),
         "extensions": json.dumps({"clientLibrary": {"name": "@apollo/client", "version": "4.1.4"},
                                  "persistedQuery": {"version": 1, "sha256Hash": H[hash_key]}}, separators=(',', ':'))}
    if u3t: p["u3t"] = u3t
    r = requests.get(API, params=p, headers=get_h(token, u3t), timeout=30)
    return sj(r), r

@app.route('/')
def idx(): return "PixAI Engine Online"
@app.route('/api/restart', methods=['POST'])
def rst(): os._exit(1)

# --- Search Models/LoRAs ---
@app.route('/api/search', methods=['POST'])
def search_mod():
    d = request.json or {}
    st, kw, sz, off = d.get("type", "ANY_LORA"), d.get("keyword", ""), int(d.get("size", 24)), int(d.get("offset", 0))
    p = {"usageType": "ALL", "keyword": kw, "size": sz, "offset": off}
    r = requests.get(f"{R2}/generation-model/search", params=p, headers=get_h(d.get("token"), d.get("u3t")), timeout=30)
    res = sj(r)
    items = []
    for n in (res.get("data") or []):
        mt = n.get("type", "")
        if st == "ANY_LORA" and mt not in ("MULTI_LORA", "USER_MULTI_LORA"): continue
        if st == "ANY_MODEL" and mt in ("MULTI_LORA", "USER_MULTI_LORA"): continue
        tb, _ = pick_thumb(n.get("media") or {})
        lat = n.get("latestAvailableVersion") or {}
        items.append({
            "name": n.get("title", ""), "id": n.get("id"), "thumb": tb,
            "usage": fmt_num(n.get("refCount")), "likes": fmt_num(n.get("likedCount")),
            "type": mt, "category": n.get("category"), "v_id": lat.get("id") or n.get("latestAvailableVersionId"),
            "trigger": (lat.get("extra") or {}).get("triggerWords", ""), "base_model": lat.get("loraBaseModelType", ""),
            "permitted": n.get("permittedUse")
        })
    return jsonify({"results": items, "has_more": bool(res.get("hasMore")), "next_offset": off + sz if res.get("hasMore") else None, "raw": res})

# --- Search Artworks ---
@app.route('/api/search_artworks', methods=['POST'])
def search_art():
    d = request.json or {}
    v = {"keyword": d.get("keyword", ""), "last": int(d.get("size", 24)), "tackLanguage": "en"}
    if d.get("cursor"): v["before"] = d["cursor"]
    res, r = apq("listArtworks", v, "ART_LIST", d.get("token"), d.get("u3t"))
    edges = (res.get("data") or {}).get("artworks", {}).get("edges", []) or []
    pi = (res.get("data") or {}).get("artworks", {}).get("pageInfo", {}) or {}
    items = []
    for e in edges:
        n = e.get("node") or {}
        tb, pub = pick_thumb(n.get("media") or {})
        au, fl = n.get("author") or {}, n.get("flag") or {}
        items.append({
            "id": n.get("id"), "title": n.get("title", "Untitled"), "thumb": tb, "url": pub,
            "author": au.get("displayName", "unknown"), "author_av": au.get("avatarSmallThumbnailMediaUrl", ""),
            "likes": fmt_num(n.get("likedCount", 0)), "views": fmt_num(n.get("views", 0)),
            "comments": fmt_num(n.get("commentCount", 0)), "date": fmt_time(n.get("createdAt")),
            "tacks": [{"id": t.get("id"), "name": t.get("displayName")} for t in (n.get("tacks") or [])],
            "blur": fl.get("shouldBlur", False), "hide_prompts": n.get("hidePrompts", False)
        })
    return jsonify({"results": items, "cursor": pi.get("startCursor") if pi.get("hasPreviousPage") else None, "has_more": bool(pi.get("hasPreviousPage")), "raw": res})

# --- Artwork Detail ---
@app.route('/api/artwork_detail', methods=['POST'])
def art_det():
    d = request.json or {}
    res, r = apq("getArtworkWithTaskDetail", {"id": str(d.get("id", "")).strip(), "tackLanguage": "en"}, "ART_DETAIL", d.get("token"), d.get("u3t"))
    aw = (res.get("data") or {}).get("artwork")
    if aw:
        for lo in (aw.get("loras") or []): lo["thumb"], _ = pick_thumb(lo.get("media") or {})
        if aw.get("model"): aw["model"]["thumb"], _ = pick_thumb(aw["model"].get("media") or {})
    return jsonify({"status": "success", "data": aw, "raw": res})

# --- Artwork Similar ---
@app.route('/api/artwork_similar', methods=['POST'])
def art_sim():
    d = request.json or {}
    r = requests.get(f"{R2}/artwork/{d.get('id')}/similar", params={"first": int(d.get("first", 6)), "retriever": "default"}, headers=get_h(d.get("token"), d.get("u3t")), timeout=30)
    res = sj(r)
    items = []
    for n in (res.get("data") or []):
        m = n.get("media") or {}
        tb, pub = pick_thumb(m)
        items.append({"id": n.get("id"), "title": n.get("title", "Untitled"), "thumb": tb, "url": pub or m.get("publicUrl", ""), "author": (n.get("author") or {}).get("displayName", "unknown"), "likes": fmt_num(n.get("likedCount", 0))})
    return jsonify({"results": items, "raw": res})

# --- FIXED: Dual-Resolution (Model ID & Version ID) ---
@app.route('/api/lora_meta', methods=['POST'])
def lora_meta():
    d = request.json or {}
    mid, tk, u3 = str(d.get("id", "")).strip(), d.get("token"), d.get("u3t")
    # Step 1: Probe as Version ID
    r1_json, _ = apq("getGenerationModelByVersionId", {"id": mid}, "META_V2", tk, u3)
    v = (r1_json.get("data") or {}).get("generationModelVersion")
    if v:
        m = v.get("model") or {}
        return jsonify({"status": "success", "resolvedType": "VERSION_ID", "v_id": v["id"], "model_id": v.get("modelId") or m.get("id"), "trigger": (v.get("extra") or {}).get("triggerWords", ""), "name": m.get("title", v.get("name", "")), "source": "v2", "raw": r1_json})
    # Step 2: Fallback probe as Model ID (Fixes PersistedQueryNotFound)
    r2_json, _ = apq("getGenerationModel", {"id": mid}, "META", tk, u3)
    m = (r2_json.get("data") or {}).get("generationModel")
    if m:
        lat = m.get("latestAvailableVersion") or {}
        trg = (lat.get("extra") or {}).get("triggerWords") or (m.get("extra") or {}).get("triggerWords", "")
        return jsonify({"status": "success", "resolvedType": "MODEL_ID", "v_id": lat.get("id"), "model_id": m.get("id"), "trigger": trg, "name": m.get("title", ""), "source": "v1", "raw": r2_json})
    return jsonify({"status": "error", "step1_raw": r1_json, "step2_raw": r2_json})

# --- Generate ---
@app.route('/api/generate', methods=['POST'])
def gen():
    d = request.json or {}
    lw, lp, trgs = {}, [], ""
    for c in (d.get("lora_configs") or []):
        vid, w, trg = str(c['v_id']), float(c['weight']), c.get('triggers', '')
        lw[vid] = w
        if trg: trgs += f"{trg}, "
        lp.append({"versionId": vid, "weight": w, "triggerWords": trg, "positionInfo": {"startIndex": 0, "endIndex": 0}})
    params = {
        "prompts": (d.get("prompt") or "") + (f", {trgs}" if trgs else ""),
        "negativePrompts": d.get("neg", ""), "modelId": d.get("modelId"),
        "width": int(d.get("w", 832)), "height": int(d.get("h", 1248)), "batchSize": int(d.get("batch", 1)),
        "seed": str(d.get("seed", "")), "priority": 1000, "lora": lw, "loraParameters": lp,
        "mediaId": d.get("mediaId"), "strength": float(d.get("strength", 0.55)),
        "samplingSteps": int(d.get("steps", 28)), "samplingMethod": d.get("sampler", "Euler a"),
        "cfgScale": float(d.get("cfg", 12.7)), "promptHelper": {"withStage": True, "userWantToEnable": True, "enable": True}
    }
    if d.get("inferenceProfile"): params["inferenceProfile"] = d["inferenceProfile"]
    payload = {"operationName": "createGenerationTask", "variables": {"parameters": params, "extra": {"naturalPrompts": str(d.get("prompt", ""))}},
               "extensions": {"clientLibrary": {"name": "@apollo/client", "version": "4.1.4"}, "persistedQuery": {"version": 1, "sha256Hash": H["GEN"]}}}
    r = requests.post(API, json=payload, headers=get_h(d.get("token"), d.get("u3t")), timeout=30)
    rj = sj(r)
    return jsonify({"status": "started", "tid": rj['data']['createGenerationTask']['id'], "req_log": payload, "raw": rj}) if 'data' in rj and rj['data'].get('createGenerationTask') else jsonify({"status": "error", "raw": rj})

# --- Check Task ---
@app.route('/api/check_task', methods=['POST'])
def chk():
    d = request.json or {}
    res, _ = apq("getTaskById", {"id": d.get("tid")}, "POLL", d.get("token"), d.get("u3t"))
    t = (res.get('data') or {}).get('task') or {}
    imgs = [i['url'] for i in (t.get('media') or {}).get('urls', []) if i.get('variant') == "PUBLIC"] if t.get('status') == "completed" else []
    return jsonify({"status": t.get('status', 'unknown'), "images": imgs, "raw": res})

# --- List Tasks ---
@app.route('/api/tasks', methods=['POST'])
def tsk():
    d = request.json or {}
    v = {"last": 30, "before": d.get("cursor"), "parameterFields": ["extra","prompts","negativePrompts","samplingSteps","samplingMethod","cfgScale","width","height","loraParameters","mediaId","strength"]}
    res, r = apq("listMyTasks", v, "LIST", d.get("token"), d.get("u3t"))
    tlist = []
    for edge in reversed((res.get('data') or {}).get('me', {}).get('tasks', {}).get('edges', []) or []):
        n = edge.get('node') or {}
        if n.get('status') != "completed": continue
        pn = n.get('parameters') or {}
        urls = (n.get('media') or {}).get('urls') or []
        tlist.append({
            "url": urls[0]['url'] if urls else "", "id": n.get('id'), "time": fmt_time(n.get('createdAt')),
            "p_orig": clean_txt((pn.get('extra') or {}).get('naturalPrompts', pn.get('prompts', ''))),
            "p_final": clean_txt(pn.get('prompts')), "neg": clean_txt(pn.get('negativePrompts')),
            "size": f"{pn.get('width')}x{pn.get('height')}", "steps": pn.get('samplingSteps'),
            "cfg": pn.get('cfgScale'), "method": pn.get('samplingMethod'),
            "ref_url": f"https://api.pixai.art/v1/media/{pn.get('mediaId')}/thumbnail" if pn.get('mediaId') else None,
            "loras": [{"t": l.get('triggerWords'), "w": l.get('weight')} for l in pn.get('loraParameters', [])]
        })
    cur = ((res.get('data') or {}).get('me', {}).get('tasks', {}).get('pageInfo') or {}).get('startCursor')
    return jsonify({"status": "success", "tasks": tlist, "cursor": cur, "raw": res, "refreshed_token": check_refresh(r)})

# --- 4th Anniversary Check-in ---
@app.route('/api/checkin_status', methods=['POST'])
def ci_st():
    r = requests.get(f"{R2}/event/4th-anniversary-2026/check-in", headers=get_h(request.json.get("token"), request.json.get("u3t")), timeout=30)
    return jsonify({"status": "success", "data": sj(r), "raw": sj(r)})

@app.route('/api/checkin_do', methods=['POST'])
def ci_do():
    r = requests.post(f"{R2}/event/4th-anniversary-2026/check-in", headers=get_h(request.json.get("token"), request.json.get("u3t")), data="", timeout=30)
    return jsonify({"status": "success", "data": sj(r), "raw": sj(r)})

@app.route('/api/checkin_claim', methods=['POST'])
def ci_cl():
    d = request.json or {}
    r = requests.post(f"{R2}/event/fourthAnniversary2026/tier-rewards/checkIn/claim", headers=get_h(d.get("token"), d.get("u3t")), json={"rewardTierId": d.get("rewardTierId", "day_1")}, timeout=30)
    return jsonify({"status": "success", "data": sj(r), "raw": sj(r)})

@app.route('/api/daily_signin', methods=['POST'])
def d_sign():
    r = requests.get(f"{R2}/event/4th-anniversary-2026/daily-sign-in", headers=get_h(request.json.get("token"), request.json.get("u3t")), timeout=30)
    return jsonify({"status": "success", "data": sj(r), "raw": sj(r)})

# --- Standard Claims & Quota ---
@app.route('/api/daily_claim', methods=['POST'])
def d_clm():
    r = requests.post(DAILY_URL, headers=get_h(request.json.get("token"), request.json.get("u3t")), data="", timeout=30)
    return jsonify({"status": "success", "raw": sj(r)})

@app.route('/api/credits', methods=['POST'])
def cred():
    res, _ = apq("getMyQuota", {}, "CRE", request.json.get("token"), request.json.get("u3t"))
    return jsonify({"credits": ((res.get('data') or {}).get('me') or {}).get('quotaAmount', 0), "raw": res})

@app.route('/api/quota', methods=['POST'])
def qta():
    r = requests.get(f"{R2}/user/me/quota", headers=get_h(request.json.get("token"), request.json.get("u3t")), timeout=30)
    return jsonify(sj(r))

# --- Social & Bonus Tasks ---
@app.route('/api/claim_old', methods=['POST'])
def clm_o():
    h, tl = get_h(request.json.get("token"), request.json.get("u3t")), []
    q = "mutation followSocialMedia($platform: String!) { followSocialMedia(platform: $platform) { success __typename } }"
    for p in ["tiktok","youtube","instagram","twitter","discord"]:
        r = requests.post(API, json={"operationName": "followSocialMedia", "variables": {"platform": p}, "query": q}, headers=h, timeout=15)
        tl.append({p: r.text}); time.sleep(0.8)
    return jsonify({"status": "success", "raw": tl})

@app.route('/api/claim_new', methods=['POST'])
def clm_n():
    h, tl = get_h(request.json.get("token"), request.json.get("u3t")), []
    for p in ["tiktok","youtube","instagram","twitter","discord"]:
        r = requests.post(REST_FOLLOW_URL, json={"platform": p}, headers=h, timeout=15)
        tl.append({p: r.text}); time.sleep(0.8)
    return jsonify({"status": "success", "raw": tl})

@app.route('/api/claim_visits', methods=['POST'])
def clm_v():
    h, tl = get_h(request.json.get("token"), request.json.get("u3t")), []
    for u in ["https://youtu.be/nFJoUWvs0ko?si=YvjDeXw5hixETOR8", "https://pixai.art/tsubaki-2"]:
        r = requests.post(REST_VISIT_URL, json={"url": u}, headers=h, timeout=15)
        tl.append({u: r.text}); time.sleep(1)
    return jsonify({"status": "success", "raw": tl})

@app.route('/api/claim_mios', methods=['POST'])
def clm_m():
    h, tl = get_h(request.json.get("token"), request.json.get("u3t")), []
    r1 = requests.post(API, json={"operationName": "rollAprilFools2026Lottery", "variables": {}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H["ROLL"]}}}, headers=h, timeout=15)
    tl.append({"lottery": r1.text})
    for i in range(3226, 3235):
        r_t = requests.post(f"https://api.pixai.art/v2/event/aprilFoolsEvent2026/tier-rewards/{i}/claim", headers=h, data="", timeout=15)
        tl.append({f"tier_{i}": r_t.status_code}); time.sleep(0.3)
    return jsonify({"status": "success", "raw": tl})

@app.route('/api/enable_18', methods=['POST'])
def en_18():
    r = requests.post(API, json={"operationName": "setPreferences", "variables": {"value": {"ageVerificationStatus": "OVER18"}}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H["18PLUS"]}}}, headers=get_h(request.json.get("token"), request.json.get("u3t")), timeout=15)
    return jsonify({"status": "success", "raw": r.text})

@app.route('/api/upload', methods=['POST'])
def upl():
    t, u3 = request.form.get("token"), request.form.get("u3t")
    f = request.files['image'].read()
    h = get_h(t, u3)
    r1 = requests.post(API, json={"operationName": "uploadMedia", "variables": {"input": {"type": "IMAGE", "provider": "S3"}}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H["UPLOAD"]}}}, headers=h, timeout=30).json()
    requests.put(r1['data']['uploadMedia']['uploadUrl'], data=f, timeout=60)
    ext_id = r1['data']['uploadMedia']['uploadUrl'].split('/')[-1].split('?')[0]
    r3 = requests.post(API, json={"operationName": "uploadMedia", "variables": {"input": {"type": "IMAGE", "provider": "S3", "externalId": ext_id}}, "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H["UPLOAD"]}}}, headers=h, timeout=30).json()
    return jsonify({"success": True, "mediaId": r3['data']['uploadMedia']['mediaId']})

# --- NEW 2026 FEATURES ---
@app.route('/api/model_features', methods=['POST'])
def m_feat():
    r = requests.get(f"{R2}/generation-model/{request.json.get('id')}/features", headers=get_h(request.json.get("token"), request.json.get("u3t")), timeout=15)
    return jsonify(sj(r))

@app.route('/api/inference_profiles', methods=['POST'])
def inf_prof():
    r = requests.get(f"{R2}/generation-model/{request.json.get('id')}/inference-profiles", headers=get_h(request.json.get("token"), request.json.get("u3t")), timeout=15)
    return jsonify(sj(r))

@app.route('/api/autocomplete_tack', methods=['POST'])
def auto_tk():
    d = request.json or {}
    r = requests.get(f"{R2}/tack/autocomplete", params={"q": d.get("q", ""), "limit": int(d.get("limit", 10)), "lang": "en"}, headers=get_h(d.get("token"), d.get("u3t")), timeout=15)
    return jsonify(sj(r))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
