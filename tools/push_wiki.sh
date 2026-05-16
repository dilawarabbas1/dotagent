#!/usr/bin/env bash
# push_wiki.sh — push wiki/ from this repo into the GitHub Wiki.
#
# Run from the dotagent repo root on a machine with GitHub auth:
#   ./tools/push_wiki.sh
#
# What it does:
#   1. Clones github.com/<owner>/<repo>.wiki.git into /tmp/<repo>.wiki
#   2. Copies wiki/*.md into the clone (replacing any existing files)
#   3. Commits + pushes
#
# GitHub creates the wiki repo lazily — make sure you've enabled Wikis in
# the repo settings AND opened the Wiki tab once (which creates the
# Home page; that step is what makes the wiki git repo exist).

set -euo pipefail

OWNER="${OWNER:-dilawarabbas1}"
REPO="${REPO:-dotagent}"
SRC_DIR="${SRC_DIR:-$(cd "$(dirname "$0")/../wiki" && pwd)}"
TMP_DIR="${TMPDIR:-/tmp}/${REPO}.wiki"

if [ ! -d "$SRC_DIR" ]; then
  echo "ERROR: wiki source directory not found at $SRC_DIR" >&2
  exit 1
fi

echo "→ wiki source: $SRC_DIR"
echo "→ target:      git@github.com:${OWNER}/${REPO}.wiki.git"
echo "→ workdir:     $TMP_DIR"

if [ -d "$TMP_DIR" ]; then
  echo "  (workdir exists; updating)"
  git -C "$TMP_DIR" fetch origin
  git -C "$TMP_DIR" reset --hard origin/master 2>/dev/null \
    || git -C "$TMP_DIR" reset --hard origin/main 2>/dev/null \
    || true
else
  echo "  (cloning)"
  git clone "git@github.com:${OWNER}/${REPO}.wiki.git" "$TMP_DIR" 2>/dev/null \
    || git clone "https://github.com/${OWNER}/${REPO}.wiki.git" "$TMP_DIR"
fi

# Stop if the wiki repo is truly empty (user hasn't enabled wikis yet)
if ! git -C "$TMP_DIR" rev-parse HEAD >/dev/null 2>&1; then
  echo "  (wiki repo is empty — creating an initial commit)"
  cd "$TMP_DIR"
  echo "# placeholder" > Home.md
  git add Home.md
  git -c user.email="dotagent-bot@local" -c user.name="dotagent" \
      commit -m "init wiki"
fi

echo "→ copying wiki files"
cp -v "$SRC_DIR"/*.md "$TMP_DIR/"

cd "$TMP_DIR"
git add -A

if git diff --cached --quiet; then
  echo "✓ wiki already up to date — nothing to push."
  exit 0
fi

git -c user.email="dotagent-bot@local" -c user.name="dotagent" \
    commit -m "docs(wiki): update from main repo wiki/ ($(date -u +%Y-%m-%dT%H:%M:%SZ))"
git push origin HEAD

echo "✓ wiki pushed → https://github.com/${OWNER}/${REPO}/wiki"
