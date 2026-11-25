#!/bin/bash
# Pawstcard journal unattended publisher (F-016). Live copy: ~/.ipe/bin/pawstcard_publish.sh — NOT in the repo (Matt 2026-10-25).
# launchd (rest.ipe.pawstcard-publish) calls this every 5 min. Nothing due -> exits quietly. Something due ->
#   fetch/reset dedicated clone -> publish (stamps NOW) -> check.sh -> commit -> push, back to back (stamp ~= go-live time).
# Never pushes if: check fails · anything is deleted · staged paths fall outside journal/ sitemap.xml llms.txt · push would not fast-forward.
# Hard failure (bad manuscript / check red / deletion / path guard) -> writes $BASE/FAILED + macOS notification and STOPS until FAILED is removed.
# Soft failure (network, non-ff push) -> retried next tick; after 3 in a row writes $BASE/SOFT_ALERT + notification.
#
#   pawstcard_publish.sh              # normal tick
#   pawstcard_publish.sh --dry-run    # everything except the real push (git push --dry-run) and the queue move; prints the report
# Test knobs: PAWSTCARD_NOW (ISO with offset) · PAWSTCARD_REMOTE · PAWSTCARD_PUB_BASE · PAWSTCARD_JOURNAL_QUEUE · PAWSTCARD_LIVE_BASE · PAWSTCARD_NO_VERIFY=1
set -u
export PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin

BASE="${PAWSTCARD_PUB_BASE:-$HOME/.ipe/pawstcard-publish}"
CLONE="$BASE/repo"
REMOTE="${PAWSTCARD_REMOTE:-https://github.com/blessu76/pawstcard-landing.git}"
QUEUE="${PAWSTCARD_JOURNAL_QUEUE:-$HOME/pawstcard-journal-queue}"
LIVE="${PAWSTCARD_LIVE_BASE:-https://pawstcard.ipe.rest}"
FAILED="$BASE/FAILED"
SOFT="$BASE/soft_fail_count"
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

mkdir -p "$BASE"
ts() { TZ=Asia/Seoul date '+%Y-%m-%d %H:%M:%S KST'; }
log() { echo "[$(ts)] $*"; }
notify() { osascript -e "display notification \"$1\" with title \"Pawstcard publish\"" >/dev/null 2>&1 || true; }

# ---- lock (mkdir is atomic; stale if its pid is gone)
LOCK="$BASE/lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  if [ -f "$LOCK/pid" ] && kill -0 "$(cat "$LOCK/pid")" 2>/dev/null; then exit 0; fi
  rm -rf "$LOCK"; mkdir "$LOCK" || exit 0
fi
echo $$ > "$LOCK/pid"
STAGE=""
trap 'rm -rf "$LOCK" ${STAGE:+"$STAGE"}' EXIT

# ---- heartbeat (gap > 20 min = the machine slept or launchd was off; launchd catches up on wake by itself)
HB="$BASE/last_tick"
if [ -f "$HB" ]; then
  gap=$(( $(date +%s) - $(stat -f %m "$HB") ))
  [ "$gap" -gt 1200 ] && log "note: ${gap}s since the previous tick (sleep / launchd gap)"
fi
touch "$HB"

hard_fail() {  # $1 = reason. Leaves the real queue and main untouched.
  log "HARD FAIL: $1"
  [ "$DRY" = 0 ] && { echo "$(ts)"; echo "$1"; } > "$FAILED"
  [ -d "$CLONE/.git" ] && git -C "$CLONE" reset --hard --quiet 2>/dev/null
  [ "$DRY" = 0 ] && notify "FAILED: $1"
  exit 1
}
soft_fail() {  # $1 = reason. Next tick retries from a clean clone.
  n=$(( $(cat "$SOFT" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$SOFT"
  log "soft fail #$n: $1 (retry next tick)"
  if [ "$n" -eq 3 ]; then { echo "$(ts)"; echo "3 soft failures in a row, last: $1"; } > "$BASE/SOFT_ALERT"; notify "3 retries failed: $1"; fi
  exit 1
}

if [ -f "$FAILED" ] && [ "$DRY" = 0 ]; then exit 0; fi   # waiting for a human to read FAILED and delete it

# ---- 1. dedicated clone = origin/main exactly (pull --rebase equivalent: there is never local work in this clone)
if [ ! -d "$CLONE/.git" ]; then
  git clone --quiet "$REMOTE" "$CLONE" || soft_fail "clone failed"
fi
git -C "$CLONE" remote set-url origin "$REMOTE" 2>/dev/null
git -C "$CLONE" fetch --quiet origin main || soft_fail "git fetch failed"
git -C "$CLONE" checkout --quiet -B main origin/main || soft_fail "checkout failed"
git -C "$CLONE" reset --hard --quiet origin/main && git -C "$CLONE" clean -fdq
cd "$CLONE" || exit 1

# ---- 2. gate: main must already carry the queue-outside-the-repo publisher (94b42f4)
if ! grep -q -- '--queue' scripts/publish_journal.py 2>/dev/null; then
  [ "$DRY" = 1 ] && log "main has no --queue publisher yet (queue-out commit not pushed): nothing to do"
  exit 0
fi

# ---- 3. self-heal: a manuscript already in main's journal/posts must not also sit in the queue (duplicate slug)
mkdir -p "$QUEUE/.published"
for f in "$QUEUE"/*.md; do
  [ -e "$f" ] || continue
  if [ -f "journal/posts/$(basename "$f")" ]; then
    if [ "$DRY" = 1 ]; then log "dry-run: would move already-published $(basename "$f") out of the queue"
    else mv "$f" "$QUEUE/.published/"; log "queue: moved already-published $(basename "$f") to .published/"; fi
  fi
done

# ---- 4. anything due? Work on a staging copy of the queue so a failed run can never lose a manuscript.
NOW_ARGS=()
# pin ONE clock reading for dry-run and real publish (slot gate window can close between them -> false hard_fail)
PAWSTCARD_NOW="${PAWSTCARD_NOW:-$(TZ=Asia/Seoul date +%Y-%m-%dT%H:%M+09:00)}"
NOW_ARGS=(--now "$PAWSTCARD_NOW")
STAGE="$(mktemp -d "$BASE/stage.XXXXXX")"
for f in "$QUEUE"/*.md; do
  [ -e "$f" ] || continue
  [ -f "journal/posts/$(basename "$f")" ] && continue
  cp "$f" "$STAGE/"
done
[ -d "$QUEUE/reviews" ] && cp -R "$QUEUE/reviews" "$STAGE/"   # Iris evidence (<queue>/reviews/<slug>.iris.json) must travel with the stage
REPORT="$(python3 scripts/publish_journal.py --queue "$STAGE" --dry-run ${NOW_ARGS[@]+"${NOW_ARGS[@]}"} 2>&1)" || hard_fail "publish dry-run failed: $(echo "$REPORT" | head -3 | tr '\n' ' ')"
WOULD="$(echo "$REPORT" | sed -n 's/^  would publish: *//p')"
if [ -z "$WOULD" ] || [ "$WOULD" = "—" ]; then
  [ "$DRY" = 1 ] && { log "nothing due"; echo "$REPORT"; }
  echo 0 > "$SOFT"; rm -f "$BASE/SOFT_ALERT"
  exit 0
fi
log "due: $WOULD"

# ---- 5. publish (stamps NOW, KST) -> check -> commit -> push — back to back
PUB="$(python3 scripts/publish_journal.py --queue "$STAGE" ${NOW_ARGS[@]+"${NOW_ARGS[@]}"} 2>&1)" || hard_fail "publish failed: $(echo "$PUB" | head -3 | tr '\n' ' ')"
echo "$PUB"
# check.sh must see the staging queue (published ones already moved out of it), not the real one
CHK="$(PAWSTCARD_JOURNAL_QUEUE="$STAGE" ./scripts/check.sh 2>&1)" || hard_fail "check.sh red: $(echo "$CHK" | tail -5 | tr '\n' ' ')"

git add journal sitemap.xml llms.txt index.html
# guards: no deletion, nothing outside the allowed paths, nothing left unstaged/untracked
DELS="$(git diff --cached --name-status | awk '$1 ~ /^D/ {print $2}')"
[ -n "$DELS" ] && hard_fail "deletions staged (never pushed): $(echo "$DELS" | tr '\n' ' ')"
BAD="$(git diff --cached --name-only | grep -v -E '^(journal/|sitemap\.xml$|llms\.txt$|index\.html$)' || true)"
[ -n "$BAD" ] && hard_fail "unexpected paths staged: $(echo "$BAD" | tr '\n' ' ')"
LEFT="$(git status --porcelain | grep -v -E '^[AM] ' || true)"
[ -n "$LEFT" ] && hard_fail "unstaged/untracked leftovers: $(echo "$LEFT" | head -3 | tr '\n' ' ')"
git diff --cached --quiet && hard_fail "publish reported due ($WOULD) but produced no diff"
SLUGS="$(git diff --cached --name-only --diff-filter=A -- journal/posts | sed 's#journal/posts/##; s#\.md$##' | tr '\n' ' ')"
[ -z "$SLUGS" ] && hard_fail "due ($WOULD) but no new journal/posts file was added"

git commit --quiet -m "feat(journal): publish ${SLUGS% }" -m "Unattended publish (launchd rest.ipe.pawstcard-publish). published_at = run time, KST." || hard_fail "git commit failed"
SHA="$(git rev-parse --short HEAD)"

if [ "$DRY" = 1 ]; then
  git push --dry-run origin HEAD:main 2>&1 | tail -2
  log "DRY RUN OK: would push $SHA ($SLUGS)"; git diff HEAD~1 --stat | tail -12
  git reset --hard --quiet origin/main
  exit 0
fi

git push --quiet origin HEAD:main || soft_fail "git push failed/rejected (will re-stamp and retry from a clean clone)"
log "PUSHED $SHA: $SLUGS"
echo 0 > "$SOFT"; rm -f "$BASE/SOFT_ALERT"
for s in $SLUGS; do [ -f "$QUEUE/$s.md" ] && mv "$QUEUE/$s.md" "$QUEUE/.published/"; done

# ---- 6. soft verification: wait for the deploy, then confirm each page is 200 (never fails the run)
[ "${PAWSTCARD_NO_VERIFY:-0}" = 1 ] && exit 0
for s in $SLUGS; do
  ok=0
  for i in $(seq 1 24); do   # up to ~12 min
    code="$(curl -s -o /dev/null -w '%{http_code}' "$LIVE/journal/en/$s/?v=$(date +%s)")"
    if [ "$code" = 200 ]; then ok=1; break; fi
    sleep 30
  done
  if [ "$ok" = 1 ]; then log "live OK: $LIVE/journal/en/$s/ -> 200"
  else log "WARN: $s not 200 after 12 min — check the Actions deploy"; echo "$(ts) $s not live after 12 min" > "$BASE/SOFT_ALERT"; notify "$s not live after 12 min"; fi
done
exit 0
