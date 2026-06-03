#!/usr/bin/env bash
# Full benchmark for merged pitch report (86 chats × 6 models).
# Requires: AWS creds (Bedrock), OpenAI API key, Anthropic API key (for Opus 4.7/4.8).
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=.

DATASETS=(core downloaded acme_foods nova_exports emails)
BASELINE_MODELS=(sonnet-4-6 opus-4-6 openai:5.4 openai:5.2)
ANTHROPIC_MODELS=(anthropic:opus-4-7 anthropic:opus-4-8)

echo "== Primary run (with baseline): ${BASELINE_MODELS[*]} =="
python3 -m harness.runner --agent so_extraction --bulk \
  --datasets "${DATASETS[@]}" \
  --models "${BASELINE_MODELS[@]}" \
  --with-baseline \
  --skip-without-expected \
  --max-workers 25 \
  --no-report-llm \
  --quiet
PRIMARY_DIR=$(ls -td results/[0-9]*Z | head -1)
echo "Primary: $PRIMARY_DIR"

echo "== Supplemental run (Anthropic API, no baseline): ${ANTHROPIC_MODELS[*]} =="
python3 -m harness.runner --agent so_extraction --bulk \
  --datasets "${DATASETS[@]}" \
  --models "${ANTHROPIC_MODELS[@]}" \
  --skip-without-expected \
  --max-workers 25 \
  --no-report-llm \
  --quiet
SUPP_DIR=$(ls -td results/[0-9]*Z | head -1)
echo "Supplemental: $SUPP_DIR"

echo "== Merge + pitch report =="
python3 scripts/merge_extraction_runs.py \
  --primary "$PRIMARY_DIR" \
  --supplemental "$SUPP_DIR"

echo "Done. Open the newest results/*/report.html (pitch deck)."
