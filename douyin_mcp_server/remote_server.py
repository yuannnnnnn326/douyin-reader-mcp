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

from .media_router import detect_platform
from .server import DouyinProcessor, resolve_asr_config


jobs: dict[str, dict[str, Any]] = {}


def _authorized(request: Request) -> bool:
    expected = os.getenv("SHORTCUT_API_KEY", "").strip()
    provided = request.headers.get("X-API-Key", "").strip()
    return bool(expected) and provided == expected


def _not_found() -> JSONResponse:
    return JSONResponse(
        {"status": "error", "error": "Not found"},
        status_code=404,
    )


def transcribe_link_sync(share_link: str) -> dict[str, Any]:
    platform = detect_platform(share_link)
    if platform != "douyin":
        raise ValueError(f"暂不支持的平台: {platform}")

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

        return {
            "status": "success",
            "platform": "douyin",
            "video_id": video_info.get("video_id"),
            "title": video_info.get("title", ""),
            "transcript": transcript.strip(),
            "provider": provider,
            "model": model,
        }
    finally:
        if audio_path is not None:
            processor.cleanup_files(audio_path)
        if video_path is not None:
            processor.cleanup_files(video_path)


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
        {"status": "accepted", "job_id": job_id},
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
        return JSONResponse({
            **(job["result"] or {}),
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
