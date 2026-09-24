# Repository cleanup checklist

This project should be published as source code + self-hosting tutorial only.

## Keep

- Dockerfile
- README.md
- .env.example
- pyproject.toml
- .gitignore
- .gitattributes
- LICENSE / NOTICE if present
- douyin_mcp_server/server.py
- douyin_mcp_server/remote_server.py
- douyin_mcp_server/media_router.py
- douyin_mcp_server/workflow.py
- douyin_mcp_server/asr_module.py
- douyin_mcp_server/capture_douyin.js
- douyin_mcp_server/__init__.py
- douyin_mcp_server/__main__.py

## Remove if they are no longer used

- old public /mcp mounting code from remote_server.py
- /post-test
- old POST /transcribe
- old POST /transcribe/start
- old /transcribe/status/*
- old secret-in-path routes:
  /shortcut/{secret}/start
  /shortcut/{secret}/status/{job_id}
- hard-coded personal Render URLs
- real API keys / secrets
- screenshots containing keys
- obsolete CI/workflow files that only served the upstream project
- stale lock files only if they no longer match the current dependency workflow

## Final public-project rule

The repository must never contain:
- the author's live Render endpoint as a required endpoint
- the author's Cloudflare credentials
- the author's SHORTCUT_API_KEY

Every reader should deploy their own instance.
