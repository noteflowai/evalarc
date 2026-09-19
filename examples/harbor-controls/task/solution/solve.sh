#!/bin/sh
set -eu
cp /solution/main.py /workspace/main.py
python3 -I -B /workspace/main.py < /workspace/requests.jsonl > /workspace/answers.jsonl
