import requests, time, json, re, os, traceback
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ================= MASTER CONFIGURATION =================
API_URL = "https://api.pixai.art/graphql"
REST    = "https://api.pixai.art/v2"
DAILY_URL = "https://api.pixai.art/v2/claim/pixai-daily-credits"
REST_FOLLOW_URL = "https://api.pixai.art/v2/quest-v2/report-social-follow"
REST_VISIT_URL  = "https://api.pixai.art/v2/quest-v2/report-visit"

H_GEN    = "7662bf96848c0cd1e03cafc5a6b61785481a55a1c92faec3a248da9195bf9d25"
H_POLL   = "2526f64c73c59fcfeff938b0f4a8b3b610f2294bc6eb6b6b281aa671ac81a08e"
H_CRE    = "9356b42a4ff6e987347a1f1ee3de7aba4bd103b1cdbfbbc4c5c5fcf52767ad66"
H_ROLL   = "f0778d88963cc4e40749a8ecd9d510808b4a14cd63fac498e7763e6d5d780e5e"
H_UPLOAD = "dd71971acde11807d01862ff1a94657479f7e833af75eac850aa2de0a14fa1fa"
H_18PLUS = "fb22173aa2a43ff08be4221a17094a1445cb212e1b1970a1cee8c37e98d38304"
H_LIST   = "cc067203ddd0846c19d9e247d837c32da498247ec252fe30828434f2f136f53d"
H_META   = "cd94c1ebc6c2ee3bb3c10e1cb7c80cbd05c4470094b10e48a539aaaf36879696"
H_SEARCH = "b7a2d663bc0381dd6eb26f8c68f702cb928bea720982f6f5553ea1629a8e871d" # OLD MODEL SEARCH

H_ART_LIST   = "4333322848527d13057adfc604ae92e3153198e7f3c42fb87ff7de91fd701f24"
H_ART_DETAIL = "247baf1bd53d4e2f370a0704eac1b980c6598b657a0a46bbbbf59d9b9350d609"

BROWSER_ID = "56e77fe10bfcfb337ef2d43bc0df330f"
UA = ("Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/149.0.0.0 Mobile Safari/537.36")

def get_h(t):
    return {
        "Authorization": f"Bearer {t.strip() if t else ''}",
        "Content-Type": "application/json",
        "x-browser-id": BROWSER_ID,
        "User-Agent": UA,
        "Accept": "*/*",
        "Origin": "https://pixai.art",
        "Referer": "https://pixai.art/"
    }

def safe_json(r):
    try: return r.json()
    except Exception:
        return {"_raw_text": r.text[:4000], "_status": r.status_code}

def req_log(method, url, params=None, body=None):
    return {"method": method, "url": url, "params": params, "body": body}

def clean_txt(text):
    if not text or text == "null": return ""
    return re.sub(r'[_*`\[\]()~>#+\-={}|.!]', '', str(text))

def format_pixai_time(ts):
    try:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ")
        return dt.strftime("%b %d, %Y %I:%M %p")
    except: return ts

def fmt_num(num):
    if not num: return "0"
    try:
        num = int(num)
        if num >= 1_000_000: return f"{num/1_000_000:.2f}m"
        if num >= 1_000:     return f"{num/1_000:.2f}k"
        return str(num)
    except: return "0"

def pick_thumb(media):
    if not media: return "", ""
    thumb, public = "", ""
    urls = media.get("urls") or []
    for u in urls:
        v = u.get("variant")
        if v == "STILL_THUMBNAIL": thumb = u.get("url", "")
        elif v == "THUMBNAIL" and not thumb: thumb = u.get("url", "")
        elif v == "PUBLIC": public = u.get("url", "")
    if not thumb:  thumb  = media.get("thumbnailUrl", "") or public
    if not public: public = media.get("publicUrl", "") or thumb
    return thumb, public

def check_refresh(resp):
    new_t = resp.cookies.get("user_token")
    return new_t if new_t else None

@app.route('/')
def index(): return "Active"

@app.route('/api/restart', methods=['POST'])
def restart(): os._exit(1)

# ================= SEARCH (MIXED LOGIC) =================
@app.route('/api/search', methods=['POST'])
def search_unified():
    try:
        d = request.json or {}
        stype   = d.get("type", "ANY_LORA")
        keyword = d.get("keyword", "")

        if stype == "ANY_MODEL":
            # ★ OLD GRAPHQL LOGIC (Fixes pagination for Models)
            cursor = d.get("cursor")
            v = {
                "first": 36, 
                "types": [stype], 
                "feed": d.get("feed", "meilisearch"), 
                "keyword": keyword, 
                "after": cursor
            }
            params = {
                "operationName": "listGenerationModels", 
                "variables": json.dumps(v), 
                "extensions": json.dumps({"clientLibrary": {"name": "@apollo/client", "version": "4.1.4"}, "persistedQuery": {"version": 1, "sha256Hash": H_SEARCH}})
            }
            r = requests.get(API_URL, params=params, headers=get_h(d.get("token")), timeout=20)
            res = safe_json(r)
            
            items = []
            edges = res.get('data', {}).get('generationModels', {}).get('edges', [])
            for e in edges:
                n = e['node']
                thumb, _ = pick_thumb(n.get('media') or {})
                items.append({
                    "name": n.get('title', ''), 
                    "id": n.get('id'), 
                    "thumb": thumb, 
                    "usage": fmt_num(n.get('refCount')), 
                    "likes": fmt_num(n.get('likedCount')), 
                    "type": n.get('type')
                })
            page = res.get('data', {}).get('generationModels', {}).get('pageInfo', {})
            
            return jsonify({
                "results": items,
                "has_more": page.get('hasNextPage', False),
                "cursor": page.get('endCursor') if page.get('hasNextPage') else None,
                "req_log": req_log("GET", API_URL, params),
                "raw": res,
                "refreshed_token": check_refresh(r)
            })

        else:
            # ★ NEW REST LOGIC FOR LORA (Fast, exact, gives v_id instantly)
            size    = int(d.get("size", 24))
            offset  = int(d.get("offset", 0))
            url = f"{REST}/generation-model/search"
            params = {"usageType": "ALL", "keyword": keyword, "size": size, "offset": offset}
            r = requests.get(url, params=params, headers=get_h(d.get("token")), timeout=20)
            res = safe_json(r)

            raw_items = res.get("data", []) or []
            if not isinstance(raw_items, list): raw_items = []
            items = []

            for n in raw_items:
                if not isinstance(n, dict): continue
                model_type = n.get("type", "")
                if model_type not in ("MULTI_LORA", "USER_MULTI_LORA"): continue

                thumb, _ = pick_thumb(n.get("media") or {})
                latest = n.get("latestAvailableVersion") or {}
                extra  = latest.get("extra") or {}

                items.append({
                    "name":       n.get("title", ""),
                    "id":         n.get("id"),
                    "thumb":      thumb,
                    "usage":      fmt_num(n.get("refCount")),
                    "likes":      fmt_num(n.get("likedCount")),
                    "type":       model_type,
                    "v_id":       latest.get("id") or n.get("latestAvailableVersionId"),
                    "trigger":    extra.get("triggerWords", ""),
                    "base_model": latest.get("loraBaseModelType", ""),
                })

            has_more = bool(res.get("hasMore", False))
            next_offset = offset + size if has_more else None

            return jsonify({
                "results":     items,
                "has_more":    has_more,
                "next_offset": next_offset,
                "req_log":     req_log("GET", url, params),
                "raw":         res,
                "refreshed_token": check_refresh(r)
            })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e), "trace": traceback.format_exc()}), 200

# ================= LORA META (Fallback for Artwork modal) =================
@app.route('/api/lora_meta', methods=['POST'])
def lora_meta():
    try:
        d = request.json or {}
        p = {
            "operationName": "getGenerationModel",
            "variables": json.dumps({"id": d.get("id")}),
            "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_META}})
        }
        r = requests.get(API_URL, params=p, headers=get_h(d.get("token")), timeout=20)
        res = safe_json(r)
        if 'errors' in res or not res.get('data'): 
            return jsonify({"status": "error", "raw": res})
        
        data = res['data']['generationModel']
        v = data['latestAvailableVersion']
        return jsonify({
            "v_id": v['id'], 
            "trigger": v['extra'].get('triggerWords', ""), 
            "name": data['title'], 
            "id": d.get("id"), 
            "refreshed_token": check_refresh(r)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 200

# ================= SEARCH (ARTWORK) =================
@app.route('/api/search_artworks', methods=['POST'])
def search_artworks():
    try:
        d = request.json or {}
        keyword = d.get("keyword", "")
        size    = int(d.get("size", 24))
        cursor  = d.get("cursor")

        variables = {"keyword": keyword, "last": size, "tackLanguage": "en"}
        if cursor: variables["before"] = cursor

        p = {
            "operationName": "listArtworks",
            "variables": json.dumps(variables),
            "extensions": json.dumps({
                "clientLibrary": {"name": "@apollo/client", "version": "4.1.4"},
                "persistedQuery": {"version": 1, "sha256Hash": H_ART_LIST}
            })
        }
        r = requests.get(API_URL, params=p, headers=get_h(d.get("token")), timeout=20)
        res = safe_json(r)

        edges = (res.get("data") or {}).get("artworks", {}).get("edges", []) or []
        page  = (res.get("data") or {}).get("artworks", {}).get("pageInfo", {}) or {}

        items = []
        for e in edges:
            n = e.get("node") or {}
            thumb, public = pick_thumb(n.get("media") or {})
            author = n.get("author") or {}
            flag   = n.get("flag") or {}
            items.append({
                "id":       n.get("id"),
                "title":    n.get("title", "Untitled"),
                "thumb":    thumb,
                "url":      public,
                "author":   author.get("displayName", "unknown"),
                "author_av": author.get("avatarSmallThumbnailMediaUrl", ""),
                "likes":    fmt_num(n.get("likedCount", 0)),
                "views":    fmt_num(n.get("views", 0) or 0),
                "comments": fmt_num(n.get("commentCount", 0) or 0),
                "date":     format_pixai_time(n.get("createdAt", "")),
                "tacks":    [{"id": t.get("id"), "name": t.get("displayName"), "cat": t.get("category")}
                             for t in (n.get("tacks") or [])],
                "blur":     flag.get("shouldBlur", False),
                "hide_prompts": n.get("hidePrompts", False),
            })

        next_cursor = page.get("startCursor") if page.get("hasPreviousPage") else None
        has_more    = bool(page.get("hasPreviousPage"))

        return jsonify({
            "results": items,
            "cursor":  next_cursor,
            "has_more": has_more,
            "req_log": req_log("GET", API_URL, p),
            "raw": res,
            "refreshed_token": check_refresh(r)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e), "trace": traceback.format_exc()}), 200

# ================= ARTWORK DETAIL =================
@app.route('/api/artwork_detail', methods=['POST'])
def artwork_detail():
    try:
        d = request.json or {}
        p = {
            "operationName": "getArtworkWithTaskDetail",
            "variables": json.dumps({"id": d.get("id"), "tackLanguage": "en"}),
            "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_ART_DETAIL}})
        }
        r = requests.get(API_URL, params=p, headers=get_h(d.get("token")), timeout=20)
        res = safe_json(r)
        artwork = res.get("data", {}).get("artwork") if "data" in res else None

        if artwork:
            for lora in (artwork.get("loras") or []):
                thumb, _ = pick_thumb(lora.get("media") or {})
                lora["thumb"] = thumb
            if artwork.get("model"):
                thumb, _ = pick_thumb(artwork["model"].get("media") or {})
                artwork["model"]["thumb"] = thumb

        return jsonify({
            "status": "success",
            "data": artwork,
            "req_log": req_log("GET", API_URL, p),
            "raw": res,
            "refreshed_token": check_refresh(r)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e), "trace": traceback.format_exc()}), 200

# ================= ARTWORK SIMILAR =================
@app.route('/api/artwork_similar', methods=['POST'])
def artwork_similar():
    try:
        d = request.json or {}
        url = f"{REST}/artwork/{d.get('id')}/similar"
        params = {"first": int(d.get("first", 6)), "retriever": "default"}
        r = requests.get(url, params=params, headers=get_h(d.get("token")), timeout=20)
        res = safe_json(r)
        items = []
        for n in res.get("data", []) or []:
            m = n.get("media") or {}
            a = n.get("author") or {}
            thumb = m.get("thumbnailUrl", "")
            if not thumb:
                urls = m.get("urls") or []
                for u in urls:
                    if u.get("variant") == "THUMBNAIL":
                        thumb = u.get("url", ""); break
                if not thumb and urls:
                    thumb = urls[0].get("url", "")
            items.append({
                "id":     n.get("id"),
                "title":  n.get("title", "Untitled"),
                "thumb":  thumb,
                "url":    m.get("publicUrl", ""),
                "author": a.get("displayName", "unknown"),
                "likes":  fmt_num(n.get("likedCount", 0)),
            })
        return jsonify({
            "results": items,
            "req_log": req_log("GET", url, params),
            "raw": res,
            "refreshed_token": check_refresh(r)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e), "trace": traceback.format_exc()}), 200

# ================= 4TH ANNIV CHECK-IN =================
@app.route('/api/checkin_status', methods=['POST'])
def checkin_status():
    try:
        url = f"{REST}/event/4th-anniversary-2026/check-in"
        r = requests.get(url, headers=get_h(request.json.get("token")), timeout=20)
        data = safe_json(r)
        return jsonify({
            "status": "success", "data": data,
            "req_log": req_log("GET", url),
            "raw": data, "refreshed_token": check_refresh(r)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 200

@app.route('/api/checkin_do', methods=['POST'])
def checkin_do():
    try:
        url = f"{REST}/event/4th-anniversary-2026/check-in"
        r = requests.post(url, headers=get_h(request.json.get("token")), data="", timeout=20)
        data = safe_json(r)
        return jsonify({
            "status": "success", "data": data,
            "req_log": req_log("POST", url),
            "raw": data, "refreshed_token": check_refresh(r)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 200

@app.route('/api/checkin_claim', methods=['POST'])
def checkin_claim():
    try:
        d = request.json or {}
        url = f"{REST}/event/fourthAnniversary2026/tier-rewards/checkIn/claim"
        body = {"rewardTierId": d.get("rewardTierId", "day_1")}
        r = requests.post(url, headers=get_h(d.get("token")), json=body, timeout=20)
        data = safe_json(r)
        return jsonify({
            "status": "success", "data": data,
            "req_log": req_log("POST", url, body=body),
            "raw": data, "refreshed_token": check_refresh(r)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 200

@app.route('/api/daily_signin', methods=['POST'])
def daily_signin():
    try:
        url = f"{REST}/event/4th-anniversary-2026/daily-sign-in"
        r = requests.get(url, headers=get_h(request.json.get("token")), timeout=20)
        data = safe_json(r)
        return jsonify({
            "status": "success", "data": data,
            "req_log": req_log("GET", url),
            "raw": data, "refreshed_token": check_refresh(r)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 200

# ================= GENERATE =================
@app.route('/api/generate', methods=['POST'])
def generate():
    try:
        d = request.json
        lora_configs = d.get("lora_configs", [])
        l_w, l_p, all_t = {}, [], ""
        for conf in lora_configs:
            vid, wgt, trg = conf['v_id'], float(conf['weight']), conf['triggers']
            l_w[vid] = wgt
            all_t += f"{trg}, "
            l_p.append({
                "versionId": vid, "weight": wgt, "triggerWords": trg,
                "positionInfo": {"startIndex": 0, "endIndex": 0}
            })
        payload = {
            "operationName": "createGenerationTask",
            "variables": {
                "parameters": {
                    "prompts": d.get("prompt") + ", " + all_t,
                    "negativePrompts": d.get("neg", ""),
                    "modelId": d.get("modelId"),
                    "width": int(d.get("w", 832)),
                    "height": int(d.get("h", 1248)),
                    "batchSize": int(d.get("batch", 1)),
                    "seed": "", "priority": 1000,
                    "lora": l_w, "loraParameters": l_p,
                    "mediaId": d.get("mediaId"),
                    "strength": float(d.get("strength", 0.55)),
                    "samplingSteps": int(d.get("steps", 28)),
                    "samplingMethod": "Euler a",
                    "cfgScale": float(d.get("cfg", 12.7)),
                    "promptHelper": {"withStage": True, "userWantToEnable": True, "enable": True}
                },
                "extra": {"naturalPrompts": str(d.get("prompt"))}
            },
            "extensions": {
                "clientLibrary": {"name": "@apollo/client", "version": "4.1.4"},
                "persistedQuery": {"version": 1, "sha256Hash": H_GEN}
            }
        }
        r = requests.post(API_URL, json=payload, headers=get_h(d.get("token")), timeout=20)
        res_raw = safe_json(r)
        if 'errors' in res_raw:
            return jsonify({"status": "error", "raw": res_raw})
        return jsonify({
            "status": "started",
            "tid": res_raw['data']['createGenerationTask']['id'],
            "req_log": payload,
            "raw": res_raw
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 200

@app.route('/api/check_task', methods=['POST'])
def check_task():
    try:
        d = request.json
        p = {
            "operationName": "getTaskById",
            "variables": json.dumps({"id": d.get("tid")}),
            "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_POLL}})
        }
        r = requests.get(API_URL, params=p, headers=get_h(d.get("token")), timeout=20)
        sr = safe_json(r)
        if 'errors' in sr: return jsonify({"status": "error", "raw": sr})
        status = sr['data']['task']['status']
        imgs = []
        if status == "completed" and sr['data']['task'].get('media'):
            imgs = [i['url'] for i in sr['data']['task']['media']['urls'] if i['variant'] == "PUBLIC"]
        return jsonify({
            "status": status,
            "images": imgs,
            "raw": sr,
            "refreshed_token": check_refresh(r)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 200

@app.route('/api/tasks', methods=['POST'])
def tasks():
    try:
        d = request.json
        t = d.get("token")
        p_fields = ["extra", "prompts", "negativePrompts", "samplingSteps", "samplingMethod",
                    "cfgScale", "width", "height", "loraParameters", "mediaId", "strength"]
        vars = {"last": 30, "before": d.get("cursor"), "parameterFields": p_fields}
        r = requests.get(API_URL, params={
            "operationName": "listMyTasks",
            "variables": json.dumps(vars),
            "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_LIST}})
        }, headers=get_h(t), timeout=20)
        resp_json = safe_json(r)

        if 'data' not in resp_json or 'me' not in resp_json['data']:
            return jsonify({"status": "error", "raw": resp_json})

        task_data = []
        for edge in reversed(resp_json['data']['me']['tasks']['edges']):
            node = edge['node']
            if node['status'] != "completed": continue
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
                "url": node['media']['urls'][0]['url'] if node.get('media') else "",
                "p_orig": clean_txt(orig_prompt),
                "p_final": clean_txt(p_node.get('prompts')),
                "neg": clean_txt(p_node.get('negativePrompts', "")),
                "id": node['id'], "time": format_pixai_time(node.get('createdAt')),
                "size": f"{p_node.get('width')}x{p_node.get('height')}",
                "steps": p_node.get('samplingSteps'),
                "cfg": p_node.get('cfgScale'),
                "method": p_node.get('samplingMethod'),
                "ref_url": f"https://api.pixai.art/v1/media/{p_node.get('mediaId')}/thumbnail" if p_node.get('mediaId') else None,
                "loras": [{"t": l.get('triggerWords'), "w": l.get('weight')} for l in p_node.get('loraParameters', [])]
            })
        return jsonify({
            "status": "success",
            "tasks": task_data,
            "cursor": resp_json['data']['me']['tasks']['pageInfo'].get('startCursor'),
            "raw": resp_json,
            "refreshed_token": check_refresh(r)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 200

@app.route('/api/daily_claim', methods=['POST'])
def daily_claim():
    try:
        r = requests.post(DAILY_URL, headers=get_h(request.json.get("token")), data="", timeout=20)
        return jsonify({"status": "success", "raw": safe_json(r), "refreshed_token": check_refresh(r)})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 200

@app.route('/api/credits', methods=['POST'])
def credits():
    try:
        p = {
            "operationName": "getMyQuota",
            "variables": "{}",
            "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": H_CRE}})
        }
        r = requests.get(API_URL, params=p, headers=get_h(request.json.get("token")), timeout=20)
        return jsonify({
            "credits": safe_json(r)['data']['me']['quotaAmount'],
            "raw": safe_json(r),
            "refreshed_token": check_refresh(r)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 200

@app.route('/api/claim_old', methods=['POST'])
def claim_old():
    try:
        h, tl = get_h(request.json.get("token")), []
        q = "mutation followSocialMedia($platform: String!) { followSocialMedia(platform: $platform) { success __typename } }"
        for p in ["tiktok", "youtube", "instagram", "twitter", "discord"]:
            r = requests.post(API_URL, json={"operationName": "followSocialMedia",
                                             "variables": {"platform": p}, "query": q}, headers=h, timeout=20)
            tl.append({p: r.text}); time.sleep(1)
        return jsonify({"status": "success", "raw": tl})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 200

@app.route('/api/claim_new', methods=['POST'])
def claim_new():
    try:
        h, tl = get_h(request.json.get("token")), []
        for p in ["tiktok", "youtube", "instagram", "twitter", "discord"]:
            r = requests.post(REST_FOLLOW_URL, json={"platform": p}, headers=h, timeout=20)
            tl.append({p: r.text}); time.sleep(1)
        return jsonify({"status": "success", "raw": tl})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 200

@app.route('/api/claim_visits', methods=['POST'])
def claim_visits():
    try:
        h, tl = get_h(request.json.get("token")), []
        for u in ["https://youtu.be/nFJoUWvs0ko?si=YvjDeXw5hixETOR8", "https://pixai.art/tsubaki-2"]:
            r = requests.post(REST_VISIT_URL, json={"url": u}, headers=h, timeout=20)
            tl.append({u: r.text}); time.sleep(1.5)
        return jsonify({"status": "success", "raw": tl})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 200

@app.route('/api/claim_mios', methods=['POST'])
def claim_mios():
    try:
        h, tl = get_h(request.json.get("token")), []
        r1 = requests.post(API_URL, json={
            "operationName": "rollAprilFools2026Lottery", "variables": {},
            "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_ROLL}}
        }, headers=h, timeout=20)
        tl.append({"lottery": r1.text})
        for i in range(3226, 3235):
            r_t = requests.post(f"https://api.pixai.art/v2/event/aprilFoolsEvent2026/tier-rewards/{i}/claim",
                                headers=h, data="", timeout=20)
            tl.append({f"tier_{i}": r_t.status_code}); time.sleep(0.5)
        return jsonify({"status": "success", "raw": tl})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 200

@app.route('/api/enable_18', methods=['POST'])
def enable_18():
    try:
        h = get_h(request.json.get("token"))
        r = requests.post(API_URL, json={
            "operationName": "setPreferences",
            "variables": {"value": {"ageVerificationStatus": "OVER18"}},
            "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_18PLUS}}
        }, headers=h, timeout=20)
        return jsonify({"status": "success", "raw": r.text})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 200

@app.route('/api/upload', methods=['POST'])
def upload():
    try:
        t, f = request.form.get("token"), request.files['image'].read()
        h = get_h(t)
        r1 = requests.post(API_URL, json={
            "operationName": "uploadMedia",
            "variables": {"input": {"type": "IMAGE", "provider": "S3"}},
            "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_UPLOAD}}
        }, headers=h, timeout=20).json()
        requests.put(r1['data']['uploadMedia']['uploadUrl'], data=f, timeout=20)
        ext_id = r1['data']['uploadMedia']['uploadUrl'].split('/')[-1].split('?')[0]
        r3 = requests.post(API_URL, json={
            "operationName": "uploadMedia",
            "variables": {"input": {"type": "IMAGE", "provider": "S3", "externalId": ext_id}},
            "extensions": {"persistedQuery": {"version": 1, "sha256Hash": H_UPLOAD}}
        }, headers=h, timeout=20).json()
        return jsonify({"success": True, "mediaId": r3['data']['uploadMedia']['mediaId']})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))