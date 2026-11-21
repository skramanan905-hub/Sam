import os
import random
import time
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

UPSTREAM_BASE_URL = os.getenv("UPSTREAM_BASE_URL", "https://api.ezmaker.ai")
CREATE_PATH = "/api/v1/aikit/create"
STATUS_PATH = "/api/v1/aikit/check-status"

DEFAULT_FN_NAME = os.getenv("DEFAULT_FN_NAME", "demo-ai-video-generator")
DEFAULT_SCENE = os.getenv("DEFAULT_SCENE", "ezmaker-v1")
DEFAULT_ORIGIN_FROM = os.getenv("DEFAULT_ORIGIN_FROM", "eb2720d2be87a1f0")
DEFAULT_THEME_VERSION = os.getenv(
    "DEFAULT_THEME_VERSION",
    "83EmcUoQTUv50LhNx0VrdcK8rcGexcP35FcZDcpgWsAXEyO4xqL5shCY6sFIWB2Q",
)

# Optional static/override tokens supplied via Render Environment Variables
STATIC_FP = os.getenv("UPSTREAM_FP", "")
STATIC_FP1 = os.getenv("UPSTREAM_FP1", "")
STATIC_X_GUIDE = os.getenv("UPSTREAM_X_GUIDE", "")

# Internally consistent browser profiles (User-Agent + Client Hints + Accept-Language)
BROWSER_PROFILES: List[Dict[str, str]] = [
    {
        "user-agent": (
            "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/154.0.0.0 Mobile Safari/537.36"
        ),
        "sec-ch-ua": '"Chromium";v="154", "Google Chrome";v="154", "Not A(Brand";v="99"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "accept-language": "en-GB,en;q=0.9,ta-IN;q=0.8,ta;q=0.7,en-US;q=0.6",
    },
    {
        "user-agent": (
            "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/145.0.0.0 Mobile Safari/537.36"
        ),
        "sec-ch-ua": '"Chromium";v="145", "Google Chrome";v="145", "Not A(Brand";v="24"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "accept-language": "en-US,en;q=0.9,ta-IN;q=0.8,ta;q=0.7",
    },
    {
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
        ),
        "sec-ch-ua": '"Chromium";v="146", "Google Chrome";v="146", "Not A(Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "accept-language": "en-US,en;q=0.9",
    },
]


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=1000)
    source_image: str = Field(..., min_length=1)
    duration: int = Field(default=4, ge=1, le=30)
    resolution: str = Field(default="540p")
    scene: str = Field(default=DEFAULT_SCENE)
    profile_index: Optional[int] = Field(default=None, ge=0)


class StatusRequest(BaseModel):
    task_id: str = Field(..., min_length=1)
    profile_index: Optional[int] = Field(default=None, ge=0)


app = FastAPI(title="AI Guest Video Generator Backend", version="1.0.0")

# Allow browser requests from your HTML frontend (restrict origins in production if desired)
allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "*")
allowed_origins = (
    ["*"]
    if allowed_origins_env.strip() == "*"
    else [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def pick_profile(profile_index: Optional[int]) -> tuple[int, Dict[str, str]]:
    if profile_index is not None:
        idx = profile_index % len(BROWSER_PROFILES)
    else:
        idx = random.randrange(len(BROWSER_PROFILES))
    return idx, BROWSER_PROFILES[idx]


def build_headers(profile: Dict[str, str], nonce: str) -> Dict[str, str]:
    now_ms = str(int(time.time() * 1000))
    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "origin": "https://ezmaker.ai",
        "referer": "https://ezmaker.ai/",
        "sec-fetch-site": "same-site",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
        # Omit zstd unless you explicitly decode zstd responses
        "accept-encoding": "gzip, deflate, br",
        "user-agent": profile["user-agent"],
        "sec-ch-ua": profile["sec-ch-ua"],
        "sec-ch-ua-mobile": profile["sec-ch-ua-mobile"],
        "sec-ch-ua-platform": profile["sec-ch-ua-platform"],
        "accept-language": profile["accept-language"],
        "x-code": now_ms,
        "nonce": nonce,
        "theme-version": DEFAULT_THEME_VERSION,
    }
    if STATIC_FP:
        headers["fp"] = STATIC_FP
    if STATIC_FP1:
        headers["fp1"] = STATIC_FP1
    if STATIC_X_GUIDE:
        headers["x-guide"] = STATIC_X_GUIDE
    return headers


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/create")
async def create_video_task(req: GenerateRequest) -> Dict[str, Any]:
    idx, profile = pick_profile(req.profile_index)
    headers = build_headers(profile, nonce=DEFAULT_FN_NAME)

    payload = {
        "fn_name": DEFAULT_FN_NAME,
        "call_type": 2,
        "input": {
            "scene": req.scene,
            "prompt": req.prompt,
            "duration": req.duration,
            "resolution": req.resolution,
            "source_image": req.source_image,
        },
        "request_from": 37,
        "origin_from": DEFAULT_ORIGIN_FROM,
    }

    url = f"{UPSTREAM_BASE_URL.rstrip('/')}{CREATE_PATH}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail={"upstream_error": exc.response.text[:500]},
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream request failed: {exc}") from exc

    task_id = (data.get("data") or {}).get("task_id")
    return {
        "profile_index": idx,
        "task_id": task_id,
        "upstream": data,
    }


@app.post("/api/status")
async def check_video_status(req: StatusRequest) -> Dict[str, Any]:
    idx, profile = pick_profile(req.profile_index)
    headers = build_headers(profile, nonce=DEFAULT_FN_NAME)

    payload = {
        "task_id": req.task_id,
        "fn_name": DEFAULT_FN_NAME,
        "call_type": 2,
        "consume_type": -1,
        "request_from": 37,
        "origin_from": DEFAULT_ORIGIN_FROM,
    }

    url = f"{UPSTREAM_BASE_URL.rstrip('/')}{STATUS_PATH}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail={"upstream_error": exc.response.text[:500]},
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Status check failed: {exc}") from exc

    inner = data.get("data") or {}
    upstream_status = inner.get("status")
    video_url = inner.get("result_image")

    # Normalize status for your HTML frontend (0 = pending/processing, 2 = completed)
    if upstream_status == 2 and video_url:
        state = "completed"
    elif inner.get("error"):
        state = "failed"
    else:
        state = "processing"

    return {
        "profile_index": idx,
        "task_id": req.task_id,
        "state": state,
        "video_url": video_url,
        "error": inner.get("error", ""),
        "upstream": data,
    }
