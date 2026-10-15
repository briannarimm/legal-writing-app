#!/bin/bash
# Backup way to open ReWord: runs it in this Terminal window. Most of the time, use
# "ReWord.app" instead (no Terminal). Build it with: python3 scripts/make_app.py
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
exec python3 app/server.py
