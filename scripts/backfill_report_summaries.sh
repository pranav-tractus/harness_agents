#!/usr/bin/env bash
# Prepend AI summary HTML into report.html for known harness run folders (requires GOOGLE_API_KEY for Gemini).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
for d in 20260511T193240Z 20260512T184755Z 20260512T191113Z; do
  echo "Summarizing results/${d} ..."
  python -m harness.report_summary --run-dir "$ROOT/results/$d"
done
echo "Done."
