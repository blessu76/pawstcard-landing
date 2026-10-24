#!/bin/sh
# Green gate for this repo: unit tests + manuscript validation. Run before every commit/push.
set -e
cd "$(dirname "$0")/.."
python3 -m unittest discover -s tests
python3 scripts/build_journal.py --check
