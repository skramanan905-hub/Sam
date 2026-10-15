import requests, time, json, re, os
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ================= MASTER CONFIGURATION =================
BASE       = "https://api.pixai.art"
API_URL    = f"{BASE}/graphql"
REST       = f"{BASE}/v2"
DAILY_URL  = f"{REST}/claim/pixai-daily-credits"
REST_FOLLOW_URL = f"{REST}/quest-v2/report-social-follow"
REST_VISIT_URL  = f"{REST}/quest-v2/report-visit"

# ---- GraphQL persisted-query hashes ----
H_GEN    = "7662bf96848c0cd1e03cafc5a6b61785481a55a1c92faec3a248da9195bf9d25"
H_POLL   = "2526f64c73c59fcfeff938b0f4a8b3b610f2294bc6eb6b6b281aa671ac81a08e"
H_SEARCH = "b7a2d663bc0381dd6eb26f8c68f702cb928bea720982f6f5553ea1629a8e871d"
H_META      = "cd94c1ebc6c2ee3bb3c10e1cb7c80cbd05c4470094b10e48a539aaaf36879696"  # OLD fallback
H_META_V2   = "48261caf4d9d4a3f3c44c1eb001429824dfa36f7b91edb113fb7468eb53947d0"  # NEW primary
H_CRE    = "9356b42a4ff6e987347a1f1ee3de7aba4bd103b1cdbfbbc4c5c5fcf52767ad66"
H_ROLL   = "f0778d88963cc4e40749a8ecd9d510808b4a14cd63fac498e7763e6d5d780e5e"
H_UPLOAD = "dd71971acde11807d01862ff1a94657479f7e833af75eac850aa2de0a14fa1fa"
H_COST   = "50567e9680327f27a692e76f62b1b3699b24467f3747b0e14d3345d2e3077395"
H_18PLUS = "fb22173aa2a43ff08be4221a17094a1445cb212e1b1970a1cee8c37e98d38304"
H_REW    = "923002464a8e816706394061c18316cd2d14f5f025dbd1d08020e44cd8a23546"
H_LIST   = "cc067203ddd0846c19d9e247d837c32da498247ec252fe30828434f2f136f53d"
H_ART_LIST   = "4333322848527d13057adfc604ae92e3153198e7f3c42fb87ff7de91fd701f24"  # listArtworks
H_ART_DETAIL = "247baf1bd53d4e2f370a0704eac1b980c6598b657a0a46bbbbf59d9b9350d609"  # getArtworkWithTaskDetail

DEFAULT_BROWSER_ID = "56e77fe10bfcfb337ef2d43bc0df330f"
UA = ("Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/149.0.0.0 Mobile Safari/537.36")

# ================= SIMPLE IN-MEMORY CACHE =================
_cache = {}
CACHE_TTL = 300  # seconds

def cached(key, url, headers, ttl=CACHE_TTL):
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit["ts"] < ttl:
        return hit["data"], True
    r = requests.get(url, headers=headers)
    data = safe_json(r)
    _cache[key] = {"ts": now, "data": data}
    return data, False

# ================= HEADERS / HELPERS =================
def get_h(t, browser_id=None):
    return {
        "Authorization": f"Bearer {t.strip()}",
        "Content-Type": "application/json",
        "x-browser-id": browser_id or DEFAULT_BROWSER_ID,
        "User-Agent": UA,
        "Accept": "application/graphql-response+json,application/json;q=0.9",
    }

def safe_json(r):
    try:
        return r.json()
    except Exception:
        return {"_raw_text": r.text[:4000], "_status": r.status_code}

def req_log(method, url, params=None, body=None):
    return {"method": method, "url": url, "params": params, "body": body}

def check_refresh(resp):
    new_t = resp.cookies.get("user_token")
    return new_t if new_t else None

def clean_txt(text):
    if not text or text == "null":
        return ""
    return re.sub(r'[_*`\[\]()~>#+\-={}|.!]', '', str(text))

def format_pixai_time(ts):
    try:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ")
        return dt.strftime("%b %d, %Y %I:%M %p")
    except Exception:
        return ts

def fmt_num(num):
    if not num:
        return "0"
    num = int(num)
    if num >= 1_000_000:
        return f"{num/1_000_000:.2f}m"
    if num >= 1_000:
        return f"{num/1_000:.2f}k"
    return str(num)

def pick_thumb(media):
    """Extract best thumbnail from PixAI media object."""
    if not media:
        return "", ""
    thumb, public = "", ""
    urls = media.get("urls") or []
    for u in urls:
        v = u.get("variant")
        if v == "STILL_THUMBNAIL":
            thumb = u.get("url", "")
        elif v == "THUMBNAIL" and not thumb:
            thumb = u.get("url", "")
        elif v == "PUBLIC":
            public = u.get("url", "")
    if not thumb:
        thumb = media.get("thumbnailUrl", "") or public
    if not public:
        public = media.get("publicUrl", "") or thumb
    return thumb, public

# ================= MISC =================
@app.route('/')
def index():
    return "Active"

@app.route('/api/restart', methods=['POST'])
def restart():
    os._exit(1)

# ================= MODEL SEARCH (REST) =================
@app.route('/api/search', methods=['POST'])
def search_models():
    d = request.json or {}
    q          = d.get("keyword", "")
    size       = int(d.get("size", 24))
    offset     = int(d.get("offset", 0))
    usage_type = d.get("usageType", "ALL")

    url = f"{REST}/generation-model/search"
    params = {"usageType": usage_type, "keyword": q, "size": size, "offset": offset}
    r = requests.get(url, params=params, headers=get_h(d.get("token"), d.get("browser_id")))
    res = safe_json(r)

    items = []
    for n in res.get("data", []) or []:
        thumb, _ = pick_thumb(n.get("media") or {})
        v = n.get("latestAvailableVersion") or {}
        extra = v.get("extra") or {}
        base_list = n.get("loraBaseModelTypes") or []
        items.append({
            "id":       n.get("id"),
            "title":    n.get("title", ""),
            "thumb":    thumb,
            "usage":    fmt_num(n.get("refCount")),
            "likes":    fmt_num(n.get("likedCount")),
            "type":     n.get("type"),
            "category": n.get("category"),
            "base":     base_list[0] if base_list else None,
            "v_id":     n.get("latestAvailableVersionId"),
            "trigger":  extra.get("triggerWords", ""),
            "permitted": n.get("permittedUse"),
        })

    return jsonify({
        "results":  items,
        "has_more": res.get("hasMore", False),
        "next_offset": offset + size,
        "req_log":  req_log("GET", url, params),
        "raw":      res,
        "refreshed_token": check_refresh(r),
    })

# ================= LORA META (2-step fallback) =================
@app.route('/api/lora_meta', methods=['POST'])
def lora_meta():
    d = request.json or {}
    token = d.get("token")
    model_id = d.get("id")
    h = get_h(token, d.get("browser_id"))

    # STEP 1: v2
    p1 = {
        "operationName": "getGenerationModelByVersionId",
        "variables": json.dumps({"id": model_id}),
        "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_META_V2}}),
    }
    r1 = requests.get(API_URL, params=p1, headers=h)
    res1 = safe_json(r1)
    if "errors" not in res1 and res1.get("data", {}).get("generationModelVersion"):
        v = res1["data"]["generationModelVersion"]
        model = v.get("model") or {}
        return jsonify({
            "v_id":    v["id"],
            "trigger": (v.get("extra") or {}).get("triggerWords", ""),
            "name":    model.get("title", v.get("name", "")),
            "id":      model_id,
            "source":  "v2",
            "req_log": req_log("GET", API_URL, p1),
            "raw":     res1,
            "refreshed_token": check_refresh(r1),
        })

    # STEP 2: v1 fallback
    p2 = {
        "operationName": "getGenerationModel",
        "variables": json.dumps({"id": model_id}),
        "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_META}}),
    }
    r2 = requests.get(API_URL, params=p2, headers=h)
    res2 = safe_json(r2)

    if "errors" in res2 or not res2.get("data", {}).get("generationModel"):
        return jsonify({
            "status": "error",
            "step1_raw": res1,
            "step2_raw": res2,
            "req_log": {"step1": req_log("GET", API_URL, p1), "step2": req_log("GET", API_URL, p2)},
            "refreshed_token": check_refresh(r2),
        })

    data = res2["data"]["generationModel"]
    v = data["latestAvailableVersion"]
    return jsonify({
        "v_id":    v["id"],
        "trigger": (v.get("extra") or {}).get("triggerWords", ""),
        "name":    data["title"],
        "id":      model_id,
        "source":  "v1",
        "req_log": {"step1": req_log("GET", API_URL, p1), "step2": req_log("GET", API_URL, p2)},
        "raw":     res2,
        "refreshed_token": check_refresh(r2),
    })

# ================= MODEL FEATURES / PROFILES =================
@app.route('/api/model_features', methods=['POST'])
def model_features():
    d = request.json or {}
    vid = d.get("id")
    url = f"{REST}/generation-model/{vid}/features"
    r = requests.get(url, headers=get_h(d.get("token"), d.get("browser_id")))
    res = safe_json(r)
    return jsonify({
        "status":  "success",
        "data":    res,
        "req_log": req_log("GET", url),
        "raw":     res,
        "refreshed_token": check_refresh(r),
    })

@app.route('/api/model_profiles', methods=['POST'])
def model_profiles():
    d = request.json or {}
    vid = d.get("id")
    url = f"{REST}/generation-model/{vid}/inference-profiles"
    r = requests.get(url, headers=get_h(d.get("token"), d.get("browser_id")))
    res = safe_json(r)
    return jsonify({
        "status":  "success",
        "data":    res,
        "req_log": req_log("GET", url),
        "raw":     res,
        "refreshed_token": check_refresh(r),
    })

# ================= ARTWORK SEARCH (with variable fallback) =================
@app.route('/api/search_artworks', methods=['POST'])
def search_artworks():
    d = request.json or {}
    q        = d.get("keyword", "")
    size     = int(d.get("size", 24))
    tack_id  = d.get("tackId")
    cursor   = d.get("cursor")          # for "next page" if API supports it

    h = get_h(d.get("token"), d.get("browser_id"))

    # Try multiple variable shapes — first non-empty wins.
    attempts = []
    if tack_id:
        attempts.append(("tackIds",   {"tackIds": [tack_id], "last": size, "tackLanguage": "en"}))
        attempts.append(("tackIds_f", {"tackIds": [tack_id], "first": size, "tackLanguage": "en"}))
    attempts.append(("keyword",   {"keyword": q, "last": size, "tackLanguage": "en"}))
    attempts.append(("keyword_f", {"keyword": q, "first": size, "tackLanguage": "en"}))
    attempts.append(("search",    {"search": q,  "last": size, "tackLanguage": "en"}))
    attempts.append(("q",         {"q": q,       "last": size, "tackLanguage": "en"}))

    edges, final_raw, used, last_req = [], None, None, None
    tried = []

    for label, vars in attempts:
        if cursor:
            vars["before"] = cursor
        p = {
            "operationName": "listArtworks",
            "variables": json.dumps(vars),
            "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_ART_LIST}}),
        }
        r = requests.get(API_URL, params=p, headers=h)
        res = safe_json(r)
        tried.append(label)
        last_req = req_log("GET", API_URL, p)
        if final_raw is None:
            final_raw = res
        e = (res.get("data") or {}).get("artworks", {}).get("edges", []) or []
        if e:
            edges = e
            final_raw = res
            used = label
            break

    items = []
    for edge in edges:
        n = edge.get("node") or {}
        thumb, public = pick_thumb(n.get("media") or {})
        author = n.get("author") or {}
        flag = n.get("flag") or {}
        tacks = n.get("tacks") or []
        items.append({
            "id":       n.get("id"),
            "title":    n.get("title", ""),
            "thumb":    thumb,
            "url":      public,
            "author":   author.get("displayName", ""),
            "author_av": author.get("avatarSmallThumbnailMediaUrl", ""),
            "likes":    fmt_num(n.get("likedCount", 0)),
            "views":    n.get("views", 0),
            "blur":     flag.get("shouldBlur", False),
            "hide_prompts": n.get("hidePrompts", False),
            "tacks":    [{"id": t.get("id"), "name": t.get("displayName"), "cat": t.get("category")} for t in tacks],
            "n_imgs":   len([u for u in (n.get("media", {}).get("urls") or []) if u.get("variant") == "PUBLIC"]),
        })

    page = ((final_raw or {}).get("data") or {}).get("artworks", {}).get("pageInfo", {}) or {}
    return jsonify({
        "results":   items,
        "cursor":    page.get("startCursor") if page.get("hasPreviousPage") else None,
        "has_more":  page.get("hasPreviousPage", False),
        "used_var":  used,
        "tried_vars": tried,
        "req_log":   last_req,
        "raw":       final_raw,
        "refreshed_token": check_refresh(r),
    })

# ================= ARTWORK DETAIL / SIMILAR =================
@app.route('/api/artwork_detail', methods=['POST'])
def artwork_detail():
    d = request.json or {}
    aid = d.get("id")
    p = {
        "operationName": "getArtworkWithTaskDetail",
        "variables": json.dumps({"id": aid, "tackLanguage": "en"}),
        "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_ART_DETAIL}}),
    }
    r = requests.get(API_URL, params=p, headers=get_h(d.get("token"), d.get("browser_id")))
    res = safe_json(r)
    return jsonify({
        "status":  "success",
        "data":    res.get("data", {}).get("artwork") if "data" in res else None,
        "req_log": req_log("GET", API_URL, p),
        "raw":     res,
        "refreshed_token": check_refresh(r),
    })

@app.route('/api/artwork_similar', methods=['POST'])
def artwork_similar():
    d = request.json or {}
    aid = d.get("id")
    first = int(d.get("first", 8))
    url = f"{REST}/artwork/{aid}/similar"
    params = {"first": first, "retriever": "default"}
    r = requests.get(url, params=params, headers=get_h(d.get("token"), d.get("browser_id")))
    res = safe_json(r)

    items = []
    for n in res.get("data", []) or []:
        media = n.get("media") or {}
        items.append({
            "id":     n.get("id"),
            "title":  n.get("title", ""),
            "thumb":  media.get("thumbnailUrl", ""),
            "url":    media.get("publicUrl", ""),
            "author": (n.get("author") or {}).get("displayName", ""),
            "likes":  fmt_num(n.get("likedCount", 0)),
        })

    return jsonify({
        "results": items,
        "req_log": req_log("GET", url, params),
        "raw":     res,
        "refreshed_token": check_refresh(r),
    })

# ================= TACK AUTOCOMPLETE / TRENDING / BATCH =================
@app.route('/api/tack_autocomplete', methods=['POST'])
def tack_autocomplete():
    d = request.json or {}
    q = d.get("q", "")
    limit = int(d.get("limit", 10))
    lang = d.get("lang", "en")
    url = f"{REST}/tack/autocomplete"
    params = {"q": q, "limit": limit, "lang": lang}
    r = requests.get(url, params=params, headers=get_h(d.get("token"), d.get("browser_id")))
    res = safe_json(r)
    items = [{
        "id":       t.get("id"),
        "code":     t.get("codeName"),
        "cat":      t.get("category"),
        "display":  t.get("displayName"),
        "default":  t.get("defaultName"),
        "count":    t.get("artworkCount", 0),
        "thumb":    t.get("thumbnailUrl"),
    } for t in (res.get("data") or [])]
    return jsonify({
        "results": items,
        "req_log": req_log("GET", url, params),
        "raw":     res,
        "refreshed_token": check_refresh(r),
    })

@app.route('/api/tack_trending', methods=['POST'])
def tack_trending():
    d = request.json or {}
    page = int(d.get("page", 1))
    size = int(d.get("pageSize", 10))
    sort = d.get("sort", "daily")
    lang = d.get("lang", "en")
    url = f"{REST}/tack/trending"
    params = {"page": page, "pageSize": size, "sort": sort, "lang": lang}
    r = requests.get(url, params=params, headers=get_h(d.get("token"), d.get("browser_id")))
    res = safe_json(r)

    items = []
    for t in res.get("data", []) or []:
        tack = t.get("tack") or {}
        counts = t.get("artworkCount") or {}
        covers = [c.get("thumbnailUrl") for c in (tack.get("coverMedias") or [])]
        items.append({
            "id":      tack.get("id"),
            "name":    tack.get("displayName"),
            "code":    tack.get("codeName"),
            "cat":     tack.get("category"),
            "thumb":   tack.get("thumbnailUrl"),
            "counts":  counts,
            "covers":  covers,
            "score":   t.get("score"),
        })
    return jsonify({
        "results": items,
        "req_log": req_log("GET", url, params),
        "raw":     res,
        "refreshed_token": check_refresh(r),
    })

@app.route('/api/tack_batch', methods=['POST'])
def tack_batch():
    d = request.json or {}
    ids = d.get("ids", [])
    lang = d.get("lang", "en")
    url = f"{REST}/tack/batch"
    params = [("ids[]", i) for i in ids] + [("lang", lang)]
    r = requests.get(url, params=params, headers=get_h(d.get("token"), d.get("browser_id")))
    res = safe_json(r)
    return jsonify({
        "results": res.get("data", []),
        "req_log": req_log("GET", url, params),
        "raw":     res,
        "refreshed_token": check_refresh(r),
    })

# ================= CONFIG CACHE =================
@app.route('/api/constants', methods=['POST'])
def constants():
    d = request.json or {}
    url = f"{BASE}/config/constants"
    data, was_cached = cached("constants", url, get_h(d.get("token"), d.get("browser_id")))
    return jsonify({
        "status": "success",
        "data":   data,
        "cached": was_cached,
        "req_log": req_log("GET", url),
        "raw":    data,
    })

@app.route('/api/event_config', methods=['POST'])
def event_config():
    d = request.json or {}
    url = f"{BASE}/config/growthEvents"
    data, was_cached = cached("growthEvents", url, get_h(d.get("token"), d.get("browser_id")))
    return jsonify({
        "status": "success",
        "data":   data,
        "cached": was_cached,
        "req_log": req_log("GET", url),
        "raw":    data,
    })

# ================= 4TH ANNIV CHECK-IN =================
@app.route('/api/checkin_status', methods=['POST'])
def checkin_status():
    d = request.json or {}
    url = f"{REST}/event/4th-anniversary-2026/check-in"
    r = requests.get(url, headers=get_h(d.get("token"), d.get("browser_id")))
    res = safe_json(r)
    return jsonify({
        "status":  "success",
        "data":    res,
        "req_log": req_log("GET", url),
        "raw":     res,
        "refreshed_token": check_refresh(r),
    })

@app.route('/api/checkin_do', methods=['POST'])
def checkin_do():
    d = request.json or {}
    url = f"{REST}/event/4th-anniversary-2026/check-in"
    r = requests.post(url, headers=get_h(d.get("token"), d.get("browser_id")), data="")
    res = safe_json(r)
    return jsonify({
        "status":  "success",
        "data":    res,
        "req_log": req_log("POST", url),
        "raw":     res,
        "refreshed_token": check_refresh(r),
    })

@app.route('/api/checkin_claim', methods=['POST'])
def checkin_claim():
    d = request.json or {}
    tid = d.get("rewardTierId", "day_1")
    url = f"{REST}/event/fourthAnniversary2026/tier-rewards/checkIn/claim"
    body = {"rewardTierId": tid}
    r = requests.post(url, headers=get_h(d.get("token"), d.get("browser_id")), json=body)
    res = safe_json(r)
    return jsonify({
        "status":  "success",
        "data":    res,
        "req_log": req_log("POST", url, body=body),
        "raw":     res,
        "refreshed_token": check_refresh(r),
    })

@app.route('/api/daily_signin', methods=['POST'])
def daily_signin():
    d = request.json or {}
    url = f"{REST}/event/4th-anniversary-2026/daily-sign-in"
    r = requests.get(url, headers=get_h(d.get("token"), d.get("browser_id")))
    res = safe_json(r)
    return jsonify({
        "status":  "success",
        "data":    res,
        "req_log": req_log("GET", url),
        "raw":     res,
        "refreshed_token": check_refresh(r),
    })

# ================= GENERATE =================
@app.route('/api/generate', methods=['POST'])
def generate():
    d = request.json or {}
    lora_configs = d.get("lora_configs", [])
    l_w, l_p, all_t = {}, [], ""
    for conf in lora_configs:
        vid, wgt, trg = conf['v_id'], float(conf['weight']), conf['triggers']
        l_w[vid] = wgt
        all_t += f"{trg}, "
        l_p.append({
            "versionId": vid, "weight": wgt, "triggerWords": trg,
            "positionInfo": {"startIndex": 0, "endIndex": 0},
        })

    payload = {
        "operationName": "createGenerationTask",
        "variables": {
            "parameters": {
                "prompts":         d.get("prompt", "") + ", " + all_t,
                "negativePrompts": d.get("neg", ""),
                "modelId":         d.get("modelId"),
                "width":           int(d.get("w", 832)),
                "height":          int(d.get("h", 1248)),
                "batchSize":       int(d.get("batch", 1)),
                "seed":            "",
                "priority":        1000,
                "lora":            l_w,
                "loraParameters":  l_p,
                "mediaId":         d.get("mediaId"),
                "strength":        float(d.get("strength", 0.55)),
                "samplingSteps":   int(d.get("steps", 28)),
                "samplingMethod":  "Euler a",
                "cfgScale":        float(d.get("cfg", 12.7)),
                "promptHelper":    {"withStage": True, "userWantToEnable": True, "enable": True},
            },
            "extra": {"naturalPrompts": str(d.get("prompt", ""))},
        },
        "extensions": {
            "clientLibrary": {"name": "@apollo/client", "version": "4.1.4"},
            "persistedQuery": {"version": 1, "sha256Hash": H_GEN},
        },
    }

    r = requests.post(API_URL, json=payload, headers=get_h(d.get("token"), d.get("browser_id")))
    res_raw = safe_json(r)
    if "errors" in res_raw:
        return jsonify({
            "status": "error",
            "req_log": req_log("POST", API_URL, body=payload),
            "raw": res_raw,
        })
    return jsonify({
        "status": "started",
        "tid": res_raw["data"]["createGenerationTask"]["id"],
        "req_log": req_log("POST", API_URL, body=payload),
        "raw": res_raw,
        "refreshed_token": check_refresh(r),
    })

# ================= CHECK TASK =================
@app.route('/api/check_task', methods=['POST'])
def check_task():
    d = request.json or {}
    p = {
        "operationName": "getTaskById",
        "variables": json.dumps({"id": d.get("tid")}),
        "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_POLL}}),
    }
    r = requests.get(API_URL, params=p, headers=get_h(d.get("token"), d.get("browser_id")))
    sr = safe_json(r)
    if "errors" in sr:
        return jsonify({
            "status": "error",
            "req_log": req_log("GET", API_URL, p),
            "raw": sr,
        })
    task = sr["data"]["task"]
    status = task["status"]
    imgs = [i["url"] for i in task["media"]["urls"] if i["variant"] == "PUBLIC"] if status == "completed" and task.get("media") else []
    return jsonify({
        "status": status,
        "images": imgs,
        "req_log": req_log("GET", API_URL, p),
        "raw": sr,
        "refreshed_token": check_refresh(r),
    })

# ================= TASK HISTORY =================
@app.route('/api/tasks', methods=['POST'])
def tasks():
    d = request.json or {}
    t = d.get("token")
    p_fields = ["extra", "prompts", "negativePrompts", "samplingSteps", "samplingMethod",
                "cfgScale", "width", "height", "loraParameters", "mediaId", "strength"]
    vars = {"last": 30, "before": d.get("cursor"), "parameterFields": p_fields}
    p = {
        "operationName": "listMyTasks",
        "variables": json.dumps(vars),
        "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_LIST}}),
    }
    r = requests.get(API_URL, params=p, headers=get_h(t, d.get("browser_id")))
    resp_json = safe_json(r)

    if 'data' not in resp_json or 'me' not in resp_json['data']:
        return jsonify({
            "status": "error",
            "req_log": req_log("GET", API_URL, p),
            "raw": resp_json,
        })

    task_data = []
    for edge in reversed(resp_json['data']['me']['tasks']['edges']):
        node = edge['node']
        if node['status'] != "completed":
            continue
        p_node = node['parameters']
        extra = p_node.get('extra', {})
        natural_data = extra.get('naturalPrompts', [])
        if isinstance(natural_data, list) and len(natural_data) > 0:
            orig_prompt = natural_data[0]
        elif isinstance(natural_data, str) and len(natural_data) > 0:
            orig_prompt = natural_data
        else:
            orig_prompt = p_node.get('prompts', '')
        task_data.append({
            "url":      node['media']['urls'][0]['url'] if node.get('media') else "",
            "p_orig":   clean_txt(orig_prompt),
            "p_final":  clean_txt(p_node.get('prompts')),
            "neg":      clean_txt(p_node.get('negativePrompts', "")),
            "id":       node['id'],
            "time":     format_pixai_time(node.get('createdAt')),
            "size":     f"{p_node.get('width')}x{p_node.get('height')}",
            "steps":    p_node.get('samplingSteps'),
            "cfg":      p_node.get('cfgScale'),
            "method":   p_node.get('samplingMethod'),
            "ref_url":  f"{REST}/media/{p_node.get('mediaId')}/thumbnail" if p_node.get('mediaId') else None,
            "loras":    [{"t": l.get('triggerWords'), "w": l.get('weight')} for l in p_node.get('loraParameters', [])],
        })

    return jsonify({
        "status":   "success",
        "tasks":    task_data,
        "cursor":   resp_json['data']['me']['tasks']['pageInfo'].get('startCursor'),
        "req_log":  req_log("GET", API_URL, p),
        "raw":      resp_json,
        "refreshed_token": check_refresh(r),
    })

# ================= CLAIM / CREDITS / QUESTS =================
@app.route('/api/daily_claim', methods=['POST'])
def daily_claim():
    d = request.json or {}
    r = requests.post(DAILY_URL, headers=get_h(d.get("token"), d.get("browser_id")), data="")
    res = safe_json(r)
    return jsonify({
        "status":  "success",
        "raw":     res,
        "req_log": req_log("POST", DAILY_URL),
        "refreshed_token": check_refresh(r),
    })

@app.route('/api/credits', methods=['POST'])
def credits():
    d = request.json or {}
    p = {
        "operationName": "getMyQuota",
        "variables": "{}",
        "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_CRE}}),
    }
    r = requests.get(API_URL, params=p, headers=get_h(d.get("token"), d.get("browser_id")))
    res = safe_json(r)
    amt = res.get('data', {}).get('me', {}).get('quotaAmount', 0)
    return jsonify({
        "credits": amt,
        "req_log": req_log("GET", API_URL, p),
        "raw":     res,
        "refreshed_token": check_refresh(r),
    })

@app.route('/api/claim_old', methods=['POST'])
def claim_old():
    d = request.json or {}
    h, tl = get_h(d.get("token"), d.get("browser_id")), []
    q = "mutation followSocialMedia($platform: String!) { followSocialMedia(platform: $platform) { success __typename } }"
    for p in ["tiktok", "youtube", "instagram", "twitter", "discord"]:
        body = {"operationName": "followSocialMedia", "variables": {"platform": p}, "query": q}
        r = requests.post(API_URL, json=body, headers=h)
        tl.append({p: safe_json(r)})
        time.sleep(1)
    return jsonify({"status": "success", "raw": tl})

@app.route('/api/claim_new', methods=['POST'])
def claim_new():
    d = request.json or {}
    h, tl = get_h(d.get("token"), d.get("browser_id")), []
    for p in ["tiktok", "youtube", "instagram", "twitter", "discord"]:
        body = {"platform": p}
        r = requests.post(REST_FOLLOW_URL, json=body, headers=h)
        tl.append({p: safe_json(r)})
        time.sleep(1)
    return jsonify({"status": "success", "raw": tl})

@app.route('/api/claim_visits', methods=['POST'])
def claim_visits():
    d = request.json or {}
    h, tl = get_h(d.get("token"), d.get("browser_id")), []
    for u in ["https://youtu.be/nFJoUWvs0ko?si=YvjDeXw5hixETOR8", "https://pixai.art/tsubaki-2"]:
        body = {"url": u}
        r = requests.post(REST_VISIT_URL, json=body, headers=h)
        tl.append({u: safe_json(r)})
        time.sleep(1.5)
    return jsonify({"status": "success", "raw": tl})

@app.route('/api/claim_mios', methods=['POST'])
def claim_mios():
    d = request.json or {}
    h, tl = get_h(d.get("token"), d.get("browser_id")), []
    body = {"operationName": "rollAprilFools2026Lottery", "variables": {},
            "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_ROLL}}}
    r1 = requests.post(API_URL, json=body, headers=h)
    tl.append({"lottery": safe_json(r1)})
    for i in range(3226, 3235):
        url = f"{REST}/event/aprilFoolsEvent2026/tier-rewards/{i}/claim"
        r_t = requests.post(url, headers=h, data="")
        tl.append({f"tier_{i}": {"status": r_t.status_code, "body": safe_json(r_t)}})
        time.sleep(0.5)
    return jsonify({"status": "success", "raw": tl})

@app.route('/api/enable_18', methods=['POST'])
def enable_18():
    d = request.json or {}
    h = get_h(d.get("token"), d.get("browser_id"))
    body = {
        "operationName": "setPreferences",
        "variables": {"value": {"ageVerificationStatus": "OVER18"}},
        "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_18PLUS}},
    }
    r = requests.post(API_URL, json=body, headers=h)
    res = safe_json(r)
    return jsonify({
        "status":  "success",
        "raw":     res,
        "req_log": req_log("POST", API_URL, body=body),
        "refreshed_token": check_refresh(r),
    })

# ================= UPLOAD =================
@app.route('/api/upload', methods=['POST'])
def upload():
    t = request.form.get("token")
    f = request.files['image'].read()
    h = get_h(t)
    p1_body = {
        "operationName": "uploadMedia",
        "variables": {"input": {"type": "IMAGE", "provider": "S3"}},
        "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_UPLOAD}},
    }
    r1 = safe_json(requests.post(API_URL, json=p1_body, headers=h))
    upload_url = r1['data']['uploadMedia']['uploadUrl']
    requests.put(upload_url, data=f)
    ext_id = upload_url.split('/')[-1].split('?')[0]
    p3_body = {
        "operationName": "uploadMedia",
        "variables": {"input": {"type": "IMAGE", "provider": "S3", "externalId": ext_id}},
        "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_UPLOAD}},
    }
    r3 = safe_json(requests.post(API_URL, json=p3_body, headers=h))
    return jsonify({
        "success": True,
        "mediaId": r3['data']['uploadMedia']['mediaId'],
        "req_log": {
            "step1": req_log("POST", API_URL, body=p1_body),
            "s3_put": req_log("PUT", upload_url),
            "step3": req_log("POST", API_URL, body=p3_body),
        },
        "raw": {"r1": r1, "r3": r3},
    })

# ================= MAIN =================
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))