#!/usr/bin/env python3
"""
Self-hosted HTTP entrypoint for the iPhone Shortcut workflow.

This file intentionally exposes only:
- GET /health
- GET /shortcut/start
- GET /shortcut/status/{job_id}

It does NOT expose a public MCP endpoint and does NOT contain any owner-specific
Render URL. Every user should deploy their own instance and use their own
Cloudflare credentials + SHORTCUT_API_KEY.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .server import DouyinProcessor, resolve_asr_config


# In-memory job store.
# Suitable for a small personal deployment. A process restart will clear jobs.
jobs: dict[str, dict[str, Any]] = {}


def _authorized(request: Request) -> bool:
    """Validate the self-hosted shortcut API key from request headers."""
    expected = os.getenv("SHORTCUT_API_KEY", "").strip()
    provided = request.headers.get("X-API-Key", "").strip()
    return bool(expected) and provided == expected


def _not_found() -> JSONResponse:
    # Avoid revealing whether a protected endpoint exists.
    return JSONResponse({"status": "error", "error": "Not found"}, status_code=404)


def _safe_unlink(path: Path | None) -> None:
    if path is None:
        return
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass


def transcribe_link_sync(share_link: str) -> dict[str, Any]:
    """
    Run the existing Douyin -> download -> audio -> Cloudflare ASR pipeline.

    The ASR provider/model is resolved by server.py. In the recommended setup,
    CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are configured on Render.
    """
    provider, api_key, model = resolve_asr_config()
    processor = DouyinProcessor(
        api_key=api_key,
        provider=provider,
        model=model,
    )

    video_path: Path | None = None
    audio_path: Path | None = None

    try:
        video_info = processor.parse_share_url(share_link)
        video_path = processor.download_video(video_info)
        audio_path = processor.extract_audio(video_path)
        transcript = processor.transcribe_audio(audio_path)

        if not transcript or not transcript.strip():
            raise RuntimeError("语音识别没有返回文本")

        return {
            "status": "success",
            "video_id": video_info.get("video_id"),
            "title": video_info.get("title", ""),
            "transcript": transcript.strip(),
            "provider": provider,
            "model": model,
        }
    finally:
        _safe_unlink(audio_path)
        _safe_unlink(video_path)


def run_job(job_id: str, share_link: str) -> None:
    jobs[job_id]["status"] = "processing"

    try:
        result = transcribe_link_sync(share_link)
        jobs[job_id] = {
            "status": "success",
            "result": result,
            "error": None,
        }
    except Exception as exc:
        jobs[job_id] = {
            "status": "failed",
            "result": None,
            "error": str(exc),
        }


async def health(_: Request) -> JSONResponse:
    return JSONResponse({
        "status": "ok",
        "service": "douyin-reader-self-hosted",
    })


async def shortcut_start(request: Request) -> JSONResponse:
    if not _authorized(request):
        return _not_found()

    share_link = request.query_params.get("url", "").strip()
    if not share_link:
        return JSONResponse(
            {"status": "error", "error": "缺少 url"},
            status_code=400,
        )

    job_id = uuid.uuid4().hex
    jobs[job_id] = {
        "status": "queued",
        "result": None,
        "error": None,
    }

    return JSONResponse(
        {
            "status": "accepted",
            "job_id": job_id,
        },
        background=BackgroundTask(run_job, job_id, share_link),
    )


async def shortcut_status(request: Request) -> JSONResponse:
    if not _authorized(request):
        return _not_found()

    job_id = request.path_params["job_id"]
    job = jobs.get(job_id)

    if not job:
        return JSONResponse(
            {
                "status": "not_found",
                "error": "任务不存在，或服务在任务期间发生过重启",
            },
            status_code=404,
        )

    if job["status"] == "success":
        result = job["result"] or {}
        # IMPORTANT: the iPhone Shortcut should test status == "success".
        return JSONResponse({
            **result,
            "status": "success",
        })

    if job["status"] == "failed":
        return JSONResponse({
            "status": "failed",
            "error": job["error"] or "未知错误",
        })

    return JSONResponse({"status": job["status"]})


routes = [
    Route("/health", health, methods=["GET"]),
    Route("/shortcut/start", shortcut_start, methods=["GET"]),
    Route("/shortcut/status/{job_id}", shortcut_status, methods=["GET"]),
]

app = Starlette(routes=routes)


def main() -> None:
    port = int(os.getenv("PORT", "10000"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
