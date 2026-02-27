#!/usr/bin/env bash
set -euo pipefail

./scripts/personality_ab_eval.py \
  --prompts docs/evals/personality-ab-prompts.json \
  --label-a composed \
  --label-b jarvis \
  --output-dir .artifacts/quality \
  --markdown \
  --enforce
