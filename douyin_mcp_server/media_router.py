from __future__ import annotations

import re
from urllib.parse import urlparse


_URL_RE = re.compile(r"https?://[^\s]+")


def extract_first_url(text: str) -> str:
    match = _URL_RE.search(text or "")
    if not match:
        raise ValueError("未找到有效 URL")
    return match.group(0).rstrip("。。，,)]}")


def detect_platform(text_or_url: str) -> str:
    url = extract_first_url(text_or_url)
    host = (urlparse(url).hostname or "").lower()

    if host == "douyin.com" or host.endswith(".douyin.com"):
        return "douyin"

    raise ValueError(f"暂不支持的平台: {host or 'unknown'}")
