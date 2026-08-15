#!/usr/bin/env bash
# Free, local, end-to-end demo of `docsmith repair` against a real Ollama
# model. Copies the sample fixture repo into a temp dir, makes a scripted
# breaking change to a documented function, and shows Docsmith propose a
# routed fix for the now-stale doc section — at $0, no API key required.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
FIXTURE_DIR="$REPO_ROOT/tests/fixtures/sample_repo"

WORK_DIR=$(mktemp -d)
cleanup() {
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT

echo "Running Docsmith repair on a local Ollama model — \$0, no API key needed."
echo "(If this is your first run: 'ollama pull qwen2.5-coder:7b' and make sure 'ollama serve' is running.)"
echo

cp -R "$FIXTURE_DIR"/. "$WORK_DIR"/

cd "$WORK_DIR"
git init -q
git -c user.name="Docsmith Demo" -c user.email="demo@docsmith.local" add -A
git -c user.name="Docsmith Demo" -c user.email="demo@docsmith.local" commit -q -m "base: sample app"
BASE=$(git rev-parse HEAD)

python3 "$REPO_ROOT/docsmith.py" build-index \
    --repo "$WORK_DIR" \
    --output "$WORK_DIR/.docsmith/index.json" \
    --no-embeddings

# Scripted signature change: add a `role` parameter to create_user(), which
# makes the README's "## Users" section (documenting the old signature) stale.
python3 - "$WORK_DIR/app.py" <<'PYEOF'
import sys

path = sys.argv[1]
with open(path) as fh:
    content = fh.read()

old_signature = 'def create_user(name: str, email: str) -> dict:'
new_signature = 'def create_user(name: str, email: str, role: str = "member") -> dict:'
if old_signature not in content:
    raise SystemExit(f"expected signature not found in {path!r}")
content = content.replace(old_signature, new_signature)
content = content.replace(
    'return {"name": name, "email": email}',
    'return {"name": name, "email": email, "role": role}',
)

with open(path, "w") as fh:
    fh.write(content)
PYEOF

git -c user.name="Docsmith Demo" -c user.email="demo@docsmith.local" add -A
git -c user.name="Docsmith Demo" -c user.email="demo@docsmith.local" commit -q -m "head: add role parameter to create_user"
HEAD=$(git rev-parse HEAD)

echo "Base commit: $BASE"
echo "Head commit: $HEAD"
echo

python3 "$REPO_ROOT/docsmith.py" repair \
    --repo "$WORK_DIR" \
    --base "$BASE" \
    --head "$HEAD" \
    --index "$WORK_DIR/.docsmith/index.json" \
    --config "$REPO_ROOT/configs/base.yaml" \
    --backend ollama
