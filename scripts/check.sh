#!/bin/sh
# Green gate for this repo: unit tests + manuscript validation. Run before every commit/push.
set -e
cd "$(dirname "$0")/.."
python3 -m unittest discover -s tests
# PAWSTCARD_NOW (ISO with offset) fakes the clock, same knob as the launchd publisher
python3 scripts/build_journal.py --check ${PAWSTCARD_NOW:+--now "$PAWSTCARD_NOW"}
