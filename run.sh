#!/bin/sh
# Run a Python file inside the lab image.
#   ./run.sh check.py
#   ./run.sh ladder/step1_one_agent.py demo-data/files/0002_bundle_scan.pdf
cd "$(dirname "$0")" || exit 1
[ -f .env ] || cp .env.example .env
docker build -q -t clearpayai-steps:lab . >/dev/null || { echo "Docker build failed: is Docker Desktop running?"; exit 1; }
# Git Bash on Windows rewrites args like /app into C:/Program Files/Git/app;
# turn that off and hand docker a Windows-style host path (D:/...) instead.
HOST_DIR=$PWD
if pwd -W >/dev/null 2>&1; then
  HOST_DIR=$(pwd -W)
  export MSYS_NO_PATHCONV=1
fi
exec docker run --rm --env-file .env -v "$HOST_DIR:/app" -w /app -e PYTHONPATH=/app clearpayai-steps:lab python "$@"