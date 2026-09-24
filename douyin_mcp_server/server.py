from __future__ import annotations

import base64
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Optional

import ffmpeg
import requests


DEFAULT_CLOUDFLARE_MODEL = "@cf/openai/whisper-large-v3-turbo"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 "
        "Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.douyin.com/",
}


def resolve_asr_config(model: Optional[str] = None) -> tuple[str, dict[str, str], str]:
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    api_token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()

    if not account_id or not api_token:
        raise ValueError(
            "缺少 Cloudflare 配置：请设置 CLOUDFLARE_ACCOUNT_ID "
            "和 CLOUDFLARE_API_TOKEN"
        )

    return (
        "cloudflare",
        {"account_id": account_id, "api_token": api_token},
        model or os.getenv("CLOUDFLARE_MODEL", DEFAULT_CLOUDFLARE_MODEL),
    )


def get_douyin_ttwid() -> str:
    url = "https://ttwid.bytedance.com/ttwid/union/register/"
    payload = {
        "region": "cn",
        "aid": 6383,
        "needFid": False,
        "service": "www.douyin.com",
        "migrate_info": {"ticket": "", "source": "node"},
        "cbUrlProtocol": "https",
        "union": True,
    }

    response = requests.post(
        url,
        json=payload,
        headers={**HEADERS, "Content-Type": "application/json"},
        timeout=15,
    )
    response.raise_for_status()

    ttwid = response.cookies.get("ttwid", "")
    if not ttwid:
        # Some responses expose Set-Cookie without populating the cookie jar.
        cookie_header = response.headers.get("Set-Cookie", "")
        match = re.search(r"(?:^|;\s*)ttwid=([^;]+)", cookie_header)
        if match:
            ttwid = match.group(1)

    if not ttwid:
        raise RuntimeError("获取抖音 ttwid 失败")

    return ttwid


def _extract_video_id(url: str) -> str:
    patterns = [
        r"/video/(\d+)",
        r"modal_id=(\d+)",
        r"aweme_id=(\d+)",
        r"item_ids=(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    match = re.search(r"\b(\d{16,22})\b", url)
    return match.group(1) if match else ""


def _find_video_item(obj):
    """Recursively locate a Douyin video item in ROUTER_DATA."""
    if isinstance(obj, dict):
        video_info_res = obj.get("videoInfoRes")
        if isinstance(video_info_res, dict):
            item_list = video_info_res.get("item_list")
            if isinstance(item_list, list) and item_list:
                return item_list[0]

        if obj.get("aweme_id") and isinstance(obj.get("video"), dict):
            return obj

        for value in obj.values():
            found = _find_video_item(value)
            if found is not None:
                return found

    elif isinstance(obj, list):
        for value in obj:
            found = _find_video_item(value)
            if found is not None:
                return found

    return None


class DouyinProcessor:
    def __init__(
        self,
        api_key: dict[str, str],
        provider: str = "cloudflare",
        model: Optional[str] = None,
    ):
        self.api_key = api_key
        self.provider = provider
        self.model = model or DEFAULT_CLOUDFLARE_MODEL
        self.temp_dir = Path(tempfile.mkdtemp(prefix="douyin-reader-"))

    def __del__(self):
        if hasattr(self, "temp_dir"):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def parse_share_url(self, share_text: str) -> dict:
        match = re.search(r"https?://[^\s]+", share_text or "")
        if not match:
            raise ValueError("未找到有效的抖音分享链接")

        share_url = match.group(0).rstrip("。。，,)]}")

        share_response = requests.get(
            share_url,
            headers=HEADERS,
            allow_redirects=True,
            timeout=20,
        )
        share_response.raise_for_status()

        video_id = _extract_video_id(share_response.url)
        if not video_id:
            video_id = _extract_video_id(share_url)
        if not video_id:
            raise ValueError("没有从抖音分享链接解析到视频 ID")

        ttwid = get_douyin_ttwid()
        page_url = f"https://www.iesdouyin.com/share/video/{video_id}"

        response = requests.get(
            page_url,
            headers=HEADERS,
            cookies={"ttwid": ttwid},
            timeout=30,
        )
        response.raise_for_status()

        match = re.search(
            r"window\._ROUTER_DATA\s*=\s*(.*?)</script>",
            response.text,
            flags=re.DOTALL,
        )
        if not match:
            raise ValueError("抖音页面中没有找到 _ROUTER_DATA")

        router_data = json.loads(match.group(1).strip())
        item = _find_video_item(router_data)
        if not item:
            raise ValueError("已取得 _ROUTER_DATA，但没有找到抖音视频作品对象")

        video = item.get("video") or {}
        play_addr = video.get("play_addr") or {}
        url_list = play_addr.get("url_list") or []

        if not url_list:
            raise ValueError("抖音作品对象中没有视频播放地址")

        video_url = url_list[0].replace("playwm", "play")
        title = (item.get("desc") or f"douyin_{video_id}").strip()
        title = re.sub(r'[\\/:*?"<>|]', "_", title)

        return {
            "url": video_url,
            "title": title,
            "video_id": str(item.get("aweme_id") or video_id),
        }

    def download_video(self, video_info: dict) -> Path:
        path = self.temp_dir / f"{video_info['video_id']}.mp4"
        with requests.get(
            video_info["url"],
            headers=HEADERS,
            stream=True,
            timeout=(15, 120),
        ) as response:
            response.raise_for_status()
            with path.open("wb") as fh:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        fh.write(chunk)

        if not path.exists() or path.stat().st_size == 0:
            raise RuntimeError("视频下载结果为空")

        return path

    def extract_audio(self, video_path: Path) -> Path:
        audio_path = video_path.with_suffix(".mp3")

        try:
            (
                ffmpeg
                .input(str(video_path))
                .output(
                    str(audio_path),
                    acodec="libmp3lame",
                    audio_bitrate="64k",
                    ac=1,
                    ar=16000,
                )
                .run(
                    capture_stdout=True,
                    capture_stderr=True,
                    overwrite_output=True,
                    quiet=True,
                )
            )
        except ffmpeg.Error as exc:
            detail = (
                exc.stderr.decode("utf-8", errors="replace")
                if exc.stderr
                else str(exc)
            )
            raise RuntimeError(f"FFmpeg 提取音频失败: {detail[-1000:]}") from exc

        if not audio_path.exists() or audio_path.stat().st_size == 0:
            raise RuntimeError("FFmpeg 没有生成有效音频")

        return audio_path

    def _audio_duration(self, audio_path: Path) -> float:
        try:
            probe = ffmpeg.probe(str(audio_path))
            duration = float((probe.get("format") or {}).get("duration") or 0)
        except Exception as exc:
            raise RuntimeError(f"读取音频时长失败: {exc}") from exc

        if duration <= 0:
            raise RuntimeError("音频时长无效")
        return duration

    def _make_audio_chunk(
        self,
        audio_path: Path,
        start: float,
        duration: float,
        index: int,
    ) -> Path:
        chunk_path = self.temp_dir / f"chunk_{index:03d}.mp3"
        try:
            (
                ffmpeg
                .input(str(audio_path), ss=start, t=duration)
                .output(
                    str(chunk_path),
                    acodec="libmp3lame",
                    audio_bitrate="64k",
                    ac=1,
                    ar=16000,
                )
                .run(
                    capture_stdout=True,
                    capture_stderr=True,
                    overwrite_output=True,
                    quiet=True,
                )
            )
        except ffmpeg.Error as exc:
            detail = (
                exc.stderr.decode("utf-8", errors="replace")
                if exc.stderr
                else str(exc)
            )
            raise RuntimeError(f"切分音频失败: {detail[-1000:]}") from exc
        return chunk_path

    def _transcribe_cloudflare(
        self,
        audio_path: Path,
        context: Optional[str] = None,
    ) -> str:
        account_id = self.api_key["account_id"]
        api_token = self.api_key["api_token"]

        endpoint = (
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
            f"/ai/run/{self.model}"
        )
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

        audio_b64 = base64.b64encode(audio_path.read_bytes()).decode("ascii")
        body = {
            "audio": audio_b64,
            "task": "transcribe",
            "language": "zh",
            "vad_filter": True,
            "condition_on_previous_text": True,
        }
        if context:
            body["initial_prompt"] = context

        response = requests.post(
            endpoint,
            headers=headers,
            json=body,
            timeout=(15, 180),
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"Cloudflare Whisper 请求失败 "
                f"(HTTP {response.status_code}): {response.text[:500]}"
            )

        payload = response.json()
        if payload.get("success") is False:
            raise RuntimeError(
                f"Cloudflare Whisper 返回失败: "
                f"{json.dumps(payload.get('errors', []), ensure_ascii=False)[:500]}"
            )

        result = payload.get("result", payload)
        text = ""

        if isinstance(result, dict):
            text = (result.get("text") or "").strip()
        elif isinstance(result, str):
            text = result.strip()

        if not text:
            raise RuntimeError("Cloudflare Whisper 没有识别到文字")

        return text

    def transcribe_audio(
        self,
        audio_path: Path,
        context: Optional[str] = None,
    ) -> str:
        if self.provider != "cloudflare":
            raise ValueError(f"当前版本不支持 ASR provider: {self.provider}")

        duration = self._audio_duration(audio_path)
        chunk_seconds = 300.0

        if duration <= chunk_seconds:
            return self._transcribe_cloudflare(audio_path, context)

        texts: list[str] = []
        start = 0.0
        index = 0

        while start < duration:
            this_duration = min(chunk_seconds, duration - start)
            chunk_path = self._make_audio_chunk(
                audio_path,
                start,
                this_duration,
                index,
            )

            try:
                text = self._transcribe_cloudflare(chunk_path, context)
                if text.strip():
                    texts.append(text.strip())
            finally:
                try:
                    chunk_path.unlink(missing_ok=True)
                except Exception:
                    pass

            start += chunk_seconds
            index += 1

        if not texts:
            raise RuntimeError("Cloudflare Whisper 没有识别到文字")

        return "\n\n".join(texts)

    def cleanup_files(self, *paths: Path) -> None:
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
