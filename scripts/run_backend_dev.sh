#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH="$(pwd)"
mkdir -p data

uvicorn firm_sim.main:app --host 127.0.0.1 --port 8000 --reload
