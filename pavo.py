import asyncio, html, io, json, os, time
import httpx
from telegram import InlineKeyboardButton as Btn, InlineKeyboardMarkup as Mk, InputFile, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import Application, CallbackQueryHandler as CQH, CommandHandler as CH, MessageHandler as MH, filters

BASE = "https://api.pixa-ai.work"
BOT_TOKEN = os.getenv("8817040407:AAHxM7D7l5Cc7yuIZvpaeS7guyIzQic9fQI") or input("Bot Token: ").strip()
ALLOW_ID = int(os.getenv("CHAT_ID") or "1827265590")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/116.0.0.0"

class Pavo:
    def __init__(self, tok, log_cb=None):
        self.tok, self.log_cb = tok, log_cb

    def hdr(self, extra=None):
        h = {
            "Authorization": f"Bearer {self.tok}",
            "Content-Type": "application/json",
            "Origin": "https://app.pavo-ai.work",
            "Referer": "https://app.pavo-ai.work/",
            "X-Platform": "1",
            "X-User-Language": "en",
            "X-App-Timezone": "Asia/Calcutta",
            "X-Client-Time-Ms": str(int(time.time() * 1000)),
            "User-Agent": UA,
        }
        if extra: h.update(extra)
        return h

    async def req(self, m, path, params=None, body=None):
        h = self.hdr()
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.request(m, f"{BASE}{path}", headers=h, params=params, json=body)
        try: rb = r.json()
        except Exception: rb = r.text
        dump = json.dumps({
            "REQ": {"m": m, "url": str(r.request.url), "hdr": h, "body": body},
            "RES": {"code": r.status_code, "hdr": dict(r.headers), "body": rb},
        }, indent=2, ensure_ascii=False)
        if self.log_cb: await self.log_cb(f"{m} {path}", dump)
        r.raise_for_status()
        if not isinstance(rb, dict) or rb.get("code") != "000000":
            raise RuntimeError(f"API Error: {rb}")
        return rb["data"]

    async def up_img(self, raw, name, ct="image/jpeg"):
        p = await self.req("POST", "/api/v1/file/presigned-url", body={
            "purpose": "chat_attachment", "content_type": ct, "filename": name
        })
        rh = p.get("required_headers") or {"Content-Type": ct}
        async with httpx.AsyncClient(timeout=60) as c:
            pr = await c.put(p["upload_url"], content=raw, headers=rh)
        if self.log_cb:
            await self.log_cb("PUT upload", json.dumps({"status": pr.status_code, "url": p["public_url"]}))
        pr.raise_for_status()
        ins = await self.req("POST", "/api/v1/file/inspect", body={"content_type": ct, "url": p["public_url"]})
        if ins.get("moderation_status") != "passed":
            raise RuntimeError(f"Moderation failed: {ins}")
        return {"url": p["public_url"], "meta_data": p["meta_data"]}

    async def sse(self, path, body, on_ev):
        h = self.hdr({"Accept": "text/event-stream", "Cache-Control": "no-cache"})
        lines, ev = [], "message"
        async with httpx.AsyncClient(timeout=120) as c:
            async with c.stream("POST", f"{BASE}{path}", headers=h, json=body) as r:
                if r.status_code >= 400:
                    err = (await r.aread()).decode("utf-8", "replace")
                    if self.log_cb: await self.log_cb(f"SSE ERR {r.status_code}", err)
                    r.raise_for_status()
                async for ln in r.aiter_lines():
                    lines.append(ln)
                    if ln.startswith("event:"): ev = ln[6:].strip()
                    elif ln.startswith("data:"):
                        try: d = json.loads(ln[5:].strip())
                        except Exception: d = {"raw": ln}
                        if on_ev: await on_ev(ev, d)
                        if ev in ("GenerationStart", "GenerationFailed", "PromptSafetyBlocked", "AgentEnd"):
                            break
        if self.log_cb:
            await self.log_cb(f"SSE {path}", json.dumps({"REQ": body, "SSE": lines}, indent=2, ensure_ascii=False))

def st(ctx):
    return ctx.user_data.setdefault("s", {
        "tok": None, "raw": True, "lraw": "", "mod": "agnes-video-new-flash",
        "mname": "Agnes Video 2.5 Flash", "mode": "omni_to_video", "rat": "9:16",
        "dur": 5, "res": "hd", "snd": True, "prm": "", "imgs": [], "cid": None,
        "wait": None, "mods": [], "spec": {}, "cred": {}
    })

def ok_user(u): return u.effective_chat and u.effective_chat.id == ALLOW_ID

async def send_raw(bot, cid, s, title, txt, force=False):
    s["lraw"] = f"=== {title} ===\n{txt}"
    if not s["raw"] and not force: return
    if len(txt) <= 3400:
        await bot.send_message(cid, f"🐞 <b>{html.escape(title)}</b>\n<pre>{html.escape(txt)}</pre>", parse_mode=ParseMode.HTML)
    else:
        b = io.BytesIO(txt.encode()); fn = "".join(c if c.isalnum() else "_" for c in title)[:30] + ".json"
        await bot.send_document(cid, InputFile(b, filename=fn), caption=f"🐞 {title}")

def cli(bot, cid, s):
    return Pavo(s["tok"], lambda t, d: send_raw(bot, cid, s, t, d))

def ui_txt(s):
    cr = s.get("cred") or {}
    pr = (s["prm"][:70] + "...") if len(s["prm"]) > 70 else (s["prm"] or "(not set)")
    return (
        f"🎬 <b>Pavo AI Studio</b>\n"
        f"• <b>Token:</b> {'✅ OK' if s['tok'] else '❌ None'} | <b>Credits:</b> {cr.get('total_balance','?')} (Eff: {cr.get('effect_quota_balance','?')})\n"
        f"• <b>Model:</b> <code>{html.escape(s['mname'])}</code>\n"
        f"• <b>Mode:</b> <code>{s['mode']}</code> | <b>Ratio:</b> <code>{s['rat']}</code> | <b>Dur:</b> <code>{s['dur']}s</code> | <b>Res:</b> <code>{s['res']}</code>\n"
        f"• <b>Sound:</b> {'🔊 ON' if s['snd'] else '🔇 OFF'} | <b>Imgs:</b> {len(s['imgs'])}/5 | <b>Raw:</b> {'🐞 ON' if s['raw'] else 'OFF'}\n"
        f"• <b>Conv:</b> <code>{s['cid'] or 'New'}</code>\n"
        f"• <b>Prompt:</b> <i>{html.escape(pr)}</i>"
    )

def ui_kb(s):
    return Mk([
        [Btn("🔑 Token", callback_data="a:tok"), Btn("💳 Credits", callback_data="a:cred")],
        [Btn("🎬 Model", callback_data="m:mod"), Btn("🎛️ Mode", callback_data="m:mode")],
        [Btn("📐 Ratio", callback_data="m:rat"), Btn("⏱️ Dur", callback_data="m:dur"), Btn("📺 Res", callback_data="m:res")],
        [Btn(f"🔊 Sound: {'ON' if s['snd'] else 'OFF'}", callback_data="a:snd"), Btn(f"🖼️ Imgs ({len(s['imgs'])})", callback_data="m:img")],
        [Btn("✍️ Prompt", callback_data="a:prm"), Btn("🧮 Cost", callback_data="a:est")],
        [Btn("📂 Projects & Watch", callback_data="m:prj:1"), Btn("🆕 New Conv", callback_data="a:new")],
        [Btn(f"🐞 Raw: {'ON' if s['raw'] else 'OFF'}", callback_data="a:raw"), Btn("📜 Last Raw", callback_data="a:lraw")],
        [Btn("🚀 GENERATE VIDEO", callback_data="a:gen")],
    ])

async def show_ui(u, ctx, edit=False):
    s = st(ctx)
    if edit and u.callback_query:
        try: await u.callback_query.edit_message_text(ui_txt(s), reply_markup=ui_kb(s), parse_mode=ParseMode.HTML)
        except BadRequest: pass
    else:
        await u.effective_chat.send_message(ui_txt(s), reply_markup=ui_kb(s), parse_mode=ParseMode.HTML)

async def cmd_start(u, ctx):
    if not ok_user(u): return
    s = st(ctx)
    if not s["tok"]:
        s["wait"] = "tok"
        await u.message.reply_text("🔑 Send your <b>Bearer JWT token</b> (from api.pixa-ai.work):", parse_mode=ParseMode.HTML)
    else:
        await show_ui(u, ctx)

async def on_txt(u, ctx):
    if not ok_user(u) or not u.message: return
    s, txt = st(ctx), u.message.text.strip()
    if s["wait"] == "tok":
        s["tok"], s["wait"] = txt.replace("Bearer ", "").strip(), None
        c = cli(ctx.bot, u.effective_chat.id, s)
        try:
            s["cred"] = await c.req("GET", "/api/v3/subscription/credits-balance")
            s["mods"] = (await c.req("GET", "/api/v1/pixa/mode_support_models", {"mode_code": "generate_video"})).get("models", [])
            s["spec"] = (await c.req("GET", "/api/v1/aigc/model-capability-spec", {"model_code": s["mod"]})).get("model", {})
            await u.message.reply_text("✅ Token verified!")
            await show_ui(u, ctx)
        except Exception as e:
            s["tok"], s["wait"] = None, "tok"
            await u.message.reply_text(f"❌ Invalid token: {e}\nSend again:")
        return
    if s["tok"]:
        s["prm"], s["wait"] = txt, None
        await u.message.reply_text("✅ Prompt updated.")
        await show_ui(u, ctx)
    else:
        s["wait"] = "tok"
        await u.message.reply_text("🔑 Send your Bearer JWT token first.")

async def on_img(u, ctx):
    if not ok_user(u) or not u.message: return
    s = st(ctx)
    if not s["tok"]: return await u.message.reply_text("🔑 Set token first (/start).")
    if len(s["imgs"]) >= 5: return await u.message.reply_text("⚠️ Max 5 images.")
    m = await u.message.reply_text("⏳ Uploading & inspecting...")
    try:
        if u.message.photo:
            f = await u.message.photo[-1].get_file()
            fn, ct = f"tg_{f.file_unique_id}.jpg", "image/jpeg"
        else:
            f = await u.message.document.get_file()
            fn, ct = u.message.document.file_name or "img.jpg", u.message.document.mime_type or "image/jpeg"
        raw = bytes(await f.download_as_bytearray())
        s["imgs"].append(await cli(ctx.bot, u.effective_chat.id, s).up_img(raw, fn, ct))
        s["wait"] = None
        await m.edit_text(f"✅ Uploaded! ({len(s['imgs'])}/5)")
        await show_ui(u, ctx)
    except Exception as e:
        await m.edit_text(f"❌ Upload failed: {e}")

def get_vids(hist):
    out = []
    for i, t in enumerate(hist.get("turns", []), 1):
        pr = next((u["data"]["content"] for u in t.get("user", []) if u.get("type") == "Message"), "")
        for a in t.get("assistant", []):
            if a.get("type") == "GenerationSuccess":
                for r in a.get("data", {}).get("data", {}).get("results", []):
                    if r.get("url"): out.append({"turn": i, "prm": pr, **r})
    return out

async def send_vid(bot, cid, url, cap):
    try:
        async with httpx.AsyncClient(timeout=180) as c:
            r = await c.get(url); r.raise_for_status()
        if len(r.content) <= 49 * 1024 * 1024:
            await bot.send_video(cid, InputFile(io.BytesIO(r.content), "video.mp4"), caption=cap, supports_streaming=True, parse_mode=ParseMode.HTML)
            return
    except Exception: pass
    await bot.send_message(cid, f"{cap}\n🔗 {html.escape(url)}", parse_mode=ParseMode.HTML)

async def run_gen(bot, cid, s, conv_id, p):
    c = cli(bot, cid, s)
    msg = await bot.send_message(cid, "🚀 Starting...")
    try:
        if not conv_id:
            t_json = json.dumps([{"type": "text", "content": p["prm"][:120]}])
            conv_id = (await c.req("POST", "/api/v1/chat/conversation", body={"title": t_json, "folder_id": "", "kb_strict": False}))["conversation_id"]
            s["cid"] = conv_id
        async def on_ev(ev, d):
            if ev == "MessageDelta" and d.get("data", {}).get("content"):
                try: await msg.edit_text(f"🤖 {html.escape(d['data']['content'])}", parse_mode=ParseMode.HTML)
                except BadRequest: pass
            elif ev == "GenerationStart":
                try: await msg.edit_text(f"⏳ Rendering <code>{d.get('task_id')}</code> (~{d.get('estimated_generation_time')}s)...", parse_mode=ParseMode.HTML)
                except BadRequest: pass
            elif ev in ("GenerationFailed", "PromptSafetyBlocked"):
                raise RuntimeError(f"{ev}: {d}")
        body = {
            "conversation_id": conv_id, "prompt": p["prm"], "mode": p["mode"], "model": p["mod"],
            "ratio": p["rat"], "duration": p["dur"], "resolution": p["res"], "sound": p["snd"],
            "creative_prompt_json": json.dumps([{"type": "text", "content": p["prm"]}]),
        }
        if p["imgs"]: body["images"] = p["imgs"]
        await c.sse("/api/v1/chat/stream", body, on_ev)
        for n in range(1, 120):
            await asyncio.sleep(15)
            h = await c.req("GET", "/api/v1/chat/conversation/history", {"conversation_id": conv_id})
            turns = h.get("turns", [])
            if not turns: continue
            for a in turns[-1].get("assistant", []):
                et, ed = a.get("type"), a.get("data", {})
                if et == "GenerationSuccess":
                    res = ed.get("data", {}).get("results", [])
                    if res:
                        r0 = res[0]
                        await msg.edit_text("📥 Sending video...")
                        await send_vid(bot, cid, r0["url"], f"✅ <b>Done!</b> <code>{ed.get('task_id')}</code>\n{r0.get('resolution')} | {r0.get('duration')}s | {r0.get('ratio')}")
                        await msg.delete(); return
                elif et == "GenerationFailed":
                    kb = Mk([[Btn("🔄 Retry", callback_data="a:gen")]])
                    return await msg.edit_text(f"❌ Failed ({ed.get('error_code')}): {html.escape(str(ed.get('error') or ed.get('error_message')))}", reply_markup=kb, parse_mode=ParseMode.HTML)
                elif et == "PromptSafetyBlocked":
                    return await msg.edit_text(f"🚫 Blocked: {html.escape(str(ed.get('error')))}", parse_mode=ParseMode.HTML)
            if n % 4 == 0:
                try: await msg.edit_text(f"⏳ Still rendering ({n*15}s)...\nConv: <code>{conv_id}</code>", parse_mode=ParseMode.HTML)
                except BadRequest: pass
    except Exception as e:
        await msg.edit_text(f"❌ Error: {html.escape(str(e))}", reply_markup=Mk([[Btn("🔄 Retry", callback_data="a:gen")]]), parse_mode=ParseMode.HTML)

async def on_cb(u, ctx):
    if not ok_user(u): return
    q = u.callback_query; await q.answer()
    s, d, cid = st(ctx), q.data, u.effective_chat.id
    if d != "a:tok" and not s["tok"]:
        s["wait"] = "tok"; return await q.edit_message_text("🔑 Send token first.")
    c = cli(ctx.bot, cid, s)

    if d == "m:home": return await show_ui(u, ctx, True)
    if d == "a:tok": s["wait"] = "tok"; return await q.edit_message_text("🔑 Send new Bearer JWT token:")
    if d == "a:prm": s["wait"] = "prm"; return await q.edit_message_text("✍️ Send text prompt:")
    if d == "a:snd": s["snd"] = not s["snd"]; return await show_ui(u, ctx, True)
    if d == "a:raw": s["raw"] = not s["raw"]; return await show_ui(u, ctx, True)
    if d == "a:new": s["cid"] = None; return await show_ui(u, ctx, True)
    if d == "a:lraw": return await send_raw(ctx.bot, cid, s, "Last Log", s["lraw"] or "Empty", True)
    if d == "a:cred":
        s["cred"] = await c.req("GET", "/api/v3/subscription/credits-balance")
        await q.message.reply_text(f"<pre>{html.escape(json.dumps(s['cred'], indent=2))}</pre>", parse_mode=ParseMode.HTML)
        return await show_ui(u, ctx, True)
    if d == "a:est":
        pl = {"model_code": s["mod"], "outputs": [{"count": 1, "media_type": "video", "resolution": s["res"], "duration_seconds": s["dur"], "gen_audio": s["snd"]}]}
        if s["imgs"]: pl["inputs"] = [{"count": len(s["imgs"]), "media_type": "image"}]
        res = await c.req("POST", "/api/v1/aigc/credits/calculate", body=pl)
        return await q.message.reply_text(f"🧮 <pre>{html.escape(json.dumps(res, indent=2))}</pre>", parse_mode=ParseMode.HTML)

    if d == "m:mod":
        mods = s["mods"] or (await c.req("GET", "/api/v1/pixa/mode_support_models", {"mode_code": "generate_video"})).get("models", [])
        s["mods"] = mods
        rows = [[Btn(f"{'✅ ' if m['code']==s['mod'] else ''}{m['name']}", callback_data=f"s:mod:{m['code']}")] for m in mods]
        rows.append([Btn("⬅️ Back", callback_data="m:home")])
        return await q.edit_message_text("🎬 <b>Select Model:</b>", reply_markup=Mk(rows), parse_mode=ParseMode.HTML)
    if d.startswith("s:mod:"):
        s["mod"] = d.split(":", 2)[2]
        for m in s["mods"]:
            if m["code"] == s["mod"]: s["mname"] = m["name"]
        s["spec"] = (await c.req("GET", "/api/v1/aigc/model-capability-spec", {"model_code": s["mod"]})).get("model", {})
        vs = s["spec"].get("video", {})
        if vs.get("duration_seconds") and s["dur"] not in vs["duration_seconds"]: s["dur"] = vs["duration_seconds"][0]
        if vs.get("aspect_ratios") and s["rat"] not in vs["aspect_ratios"]: s["rat"] = vs["aspect_ratios"][0]
        if vs.get("supported_resolutions") and s["res"] not in vs["supported_resolutions"]: s["res"] = vs["supported_resolutions"][0]
        return await show_ui(u, ctx, True)

    if d == "m:mode":
        ms = next((m.get("modes") for m in s["mods"] if m["code"] == s["mod"] and m.get("modes")), ["omni_to_video", "frames_to_video"])
        rows = [[Btn(f"{'✅ ' if x==s['mode'] else ''}{x}", callback_data=f"s:mode:{x}")] for x in ms] + [[Btn("⬅️ Back", callback_data="m:home")]]
        return await q.edit_message_text("🎛️ <b>Mode:</b>", reply_markup=Mk(rows), parse_mode=ParseMode.HTML)
    if d.startswith("s:mode:"): s["mode"] = d.split(":", 2)[2]; return await show_ui(u, ctx, True)

    if d == "m:rat":
        rs = (s["spec"] or (await c.req("GET", "/api/v1/aigc/model-capability-spec", {"model_code": s["mod"]})).get("model", {})).get("video", {}).get("aspect_ratios", ["9:16","3:4","1:1","4:3","16:9","21:9"])
        bs = [Btn(f"{'✅ ' if r==s['rat'] else ''}{r}", callback_data=f"s:rat:{r}") for r in rs]
        return await q.edit_message_text("📐 <b>Ratio:</b>", reply_markup=Mk([bs[i:i+3] for i in range(0, len(bs), 3)] + [[Btn("⬅️ Back", callback_data="m:home")]]), parse_mode=ParseMode.HTML)
    if d.startswith("s:rat:"): s["rat"] = d.split(":", 2)[2]; return await show_ui(u, ctx, True)

    if d == "m:dur":
        ds = (s["spec"] or {}).get("video", {}).get("duration_seconds", list(range(4, 13)))
        bs = [Btn(f"{'✅ ' if x==s['dur'] else ''}{x}s", callback_data=f"s:dur:{x}") for x in ds]
        return await q.edit_message_text("⏱️ <b>Duration:</b>", reply_markup=Mk([bs[i:i+3] for i in range(0, len(bs), 3)] + [[Btn("⬅️ Back", callback_data="m:home")]]), parse_mode=ParseMode.HTML)
    if d.startswith("s:dur:"): s["dur"] = int(d.split(":", 2)[2]); return await show_ui(u, ctx, True)

    if d == "m:res":
        rl = (s["spec"] or {}).get("video", {}).get("supported_resolutions", ["hd"])
        rows = [[Btn(f"{'✅ ' if x==s['res'] else ''}{x}", callback_data=f"s:res:{x}")] for x in rl] + [[Btn("⬅️ Back", callback_data="m:home")]]
        return await q.edit_message_text("📺 <b>Resolution:</b>", reply_markup=Mk(rows), parse_mode=ParseMode.HTML)
    if d.startswith("s:res:"): s["res"] = d.split(":", 2)[2]; return await show_ui(u, ctx, True)

    if d == "m:img":
        names = "\n".join(x["meta_data"].get("original_filename", "img") for x in s["imgs"]) or "None"
        kb = Mk([[Btn("➕ Upload", callback_data="a:img"), Btn("🗑️ Clear", callback_data="a:cimg")], [Btn("⬅️ Back", callback_data="m:home")]])
        return await q.edit_message_text(f"🖼️ <b>Images ({len(s['imgs'])}/5)</b>\n{html.escape(names)}", reply_markup=kb, parse_mode=ParseMode.HTML)
    if d == "a:img": s["wait"] = "img"; return await q.edit_message_text("📷 Send photo/image file now:")
    if d == "a:cimg": s["imgs"] = []; return await show_ui(u, ctx, True)

    if d.startswith("m:prj:"):
        pg = int(d.split(":")[2])
        items = (await c.req("GET", "/api/v1/chat/projects", {"page_size": 10, "page": pg})).get("list", [])
        rows = [[Btn(f"[{i['data'].get('status','?')}] {(i['data'].get('title') or 'Untitled')[:26]}", callback_data=f"c:open:{i['data']['conversation_id']}")] for i in items]
        nav = ([Btn("⬅️", callback_data=f"m:prj:{pg-1}")] if pg > 1 else []) + ([Btn("➡️", callback_data=f"m:prj:{pg+1}")] if len(items) == 10 else [])
        if nav: rows.append(nav)
        rows.append([Btn("⬅️ Studio", callback_data="m:home")])
        return await q.edit_message_text("📂 <b>Projects:</b>", reply_markup=Mk(rows), parse_mode=ParseMode.HTML)

    if d.startswith("c:open:"):
        cv = d.split(":", 2)[2]
        h = await c.req("GET", "/api/v1/chat/conversation/history", {"conversation_id": cv})
        ctx.user_data["hist"] = h
        vids = get_vids(h)
        rows = [[Btn(f"▶️ Watch #{i+1} ({v.get('duration')}s {v.get('resolution')})", callback_data=f"c:watch:{i}")] for i, v in enumerate(vids)]
        rows.append([Btn("✍️ Use Conv", callback_data=f"c:use:{cv}"), Btn("🔄 Refresh", callback_data=f"c:open:{cv}")])
        if h.get("is_running"): rows.append([Btn("📡 Resume", callback_data=f"c:res:{cv}")])
        rows.append([Btn("⬅️ Projects", callback_data="m:prj:1")])
        return await q.edit_message_text(f"💬 <b>Conv</b> <code>{cv}</code>\nTurns: {len(h.get('turns',[]))} | Running: {h.get('is_running')} | Videos: {len(vids)}", reply_markup=Mk(rows), parse_mode=ParseMode.HTML)
    if d.startswith("c:use:"): s["cid"] = d.split(":", 2)[2]; return await show_ui(u, ctx, True)
    if d.startswith("c:res:"):
        await c.sse("/api/v1/chat/stream/resume", {"conversation_id": d.split(":", 2)[2], "from_seq": 0}, None)
        return await q.message.reply_text("📡 Resume checked.")
    if d.startswith("c:watch:"):
        vids = get_vids(ctx.user_data.get("hist", {}))
        idx = int(d.split(":")[2])
        if idx >= len(vids): return await q.message.reply_text("Video not found.")
        v = vids[idx]
        await q.message.reply_text("⏳ Fetching video...")
        return await send_vid(ctx.bot, cid, v["url"], f"🎬 Turn {v['turn']} | {v.get('resolution')} {v.get('duration')}s\n<i>{html.escape(v['prm'])}</i>")

    if d == "a:gen":
        if not s["prm"]: s["wait"] = "prm"; return await q.edit_message_text("✍️ Send a prompt first:")
        p = {"prm": s["prm"], "mode": s["mode"], "mod": s["mod"], "rat": s["rat"], "dur": s["dur"], "res": s["res"], "snd": s["snd"], "imgs": list(s["imgs"])}
        ctx.application.create_task(run_gen(ctx.bot, cid, s, s["cid"], p))

app = Application.builder().token(BOT_TOKEN).build()
app.add_handler(CH("start", cmd_start))
app.add_handler(CH("menu", lambda u, c: show_ui(u, c) if ok_user(u) else None))
app.add_handler(CQH(on_cb))
app.add_handler(MH(filters.PHOTO | filters.Document.IMAGE, on_img))
app.add_handler(MH(filters.TEXT & ~filters.COMMAND, on_txt))
print("Bot running in Termux...")
app.run_polling()
