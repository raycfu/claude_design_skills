#!/usr/bin/env bash
# One-time setup for the effects skill. Safe to run again: it prints READY when everything is in place.
# Works on Mac, Linux and Windows (Git Bash). On Windows the Python lives at .venv/Scripts/python.exe.
set -e
cd "$(dirname "$0")/.."

if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  echo "NEED_FFMPEG: install ffmpeg first (Mac: brew install ffmpeg, Windows: winget install ffmpeg, Linux: sudo apt install ffmpeg)"; exit 1
fi

venv_py() { if [ -x .venv/Scripts/python.exe ]; then echo .venv/Scripts/python.exe; else echo .venv/bin/python; fi; }
CHECK="import mediapipe, cv2, PIL, numpy, onnxruntime"
VPY="$(venv_py)"
if [ -x "$VPY" ] && "$VPY" -c "$CHECK" 2>/dev/null; then echo READY; exit 0; fi

PY=""
for v in python3.12 python3.11 python3.10 python3.13 python3 python py; do
  if command -v "$v" >/dev/null 2>&1 && "$v" -c 'import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) else 1)' 2>/dev/null; then PY="$v"; break; fi
done

install_failed() {
  echo "NEED_PYTHON_312: the Python packages did not install with $1. Install Python 3.12 (Mac: brew install python@3.12, Windows: winget install Python.Python.3.12, or python.org/downloads), then run this again."
  rm -rf .venv; exit 1
}

if [ -n "$PY" ]; then
  "$PY" -m venv .venv
  VPY="$(venv_py)"
  "$VPY" -m pip install -q --upgrade pip || true
  "$VPY" -m pip install -q -r requirements.txt || install_failed "$PY"
elif command -v uv >/dev/null 2>&1; then
  uv venv -q -p 3.12 .venv
  VPY="$(venv_py)"
  uv pip install -q -p "$VPY" -r requirements.txt || install_failed "uv"
else
  echo "NEED_PYTHON: install Python 3.12 (Mac: brew install python@3.12, Windows: winget install Python.Python.3.12, or python.org/downloads), then run this again"; exit 1
fi

# Optional: Robust Video Matting for cleaner hair and edges (GPL-3.0, downloaded, not bundled). Falls back to MediaPipe if missing.
if [ ! -f models/rvm_mobilenetv3_fp32.onnx ]; then
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL -m 180 -o models/rvm_mobilenetv3_fp32.onnx https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_mobilenetv3_fp32.onnx 2>/dev/null || rm -f models/rvm_mobilenetv3_fp32.onnx
  else
    "$VPY" -c "import urllib.request as u; u.urlretrieve('https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_mobilenetv3_fp32.onnx', 'models/rvm_mobilenetv3_fp32.onnx')" 2>/dev/null || rm -f models/rvm_mobilenetv3_fp32.onnx
  fi
fi
[ -f models/rvm_mobilenetv3_fp32.onnx ] || echo "NOTE: could not download the cleaner cutout model; using the standard one. Run setup again later to retry."
"$VPY" -c "$CHECK; print('READY')"
