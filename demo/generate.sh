#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ASSETS_DIR="$PROJECT_ROOT/assets"
TAPES=("hero" "queue" "queue-simple")

# --- Dependency checks ---
if ! command -v vhs &> /dev/null; then
    echo "Error: VHS is not installed."
    echo "Install with: brew install vhs"
    echo "Or see: https://github.com/charmbracelet/vhs"
    exit 1
fi

if ! command -v gitfc &> /dev/null; then
    echo "Error: gitfc is not installed."
    echo "Install with: pip install -e . (from the project root)"
    exit 1
fi

# --- Create temp demo environment with a clean name ---
DEMO_DIR="/tmp/my-project"
rm -rf "$DEMO_DIR"
mkdir -p "$DEMO_DIR"
trap 'rm -rf "$DEMO_DIR"' EXIT

git -C "$DEMO_DIR" init --quiet
git -C "$DEMO_DIR" config user.name "demo"
git -C "$DEMO_DIR" config user.email "demo@example.com"
git -C "$DEMO_DIR" commit --allow-empty -m "init" --quiet

echo "Demo directory: $DEMO_DIR"
echo "Generating GIFs..."
echo ""

# --- Create assets directory ---
mkdir -p "$ASSETS_DIR"

# --- Run each tape ---
for tape in "${TAPES[@]}"; do
    TAPE_FILE="$SCRIPT_DIR/${tape}.tape"
    if [ ! -f "$TAPE_FILE" ]; then
        echo "Warning: $TAPE_FILE not found, skipping."
        continue
    fi

    echo "  Recording ${tape}.gif..."

    # Clean queue state before each tape
    rm -rf "$DEMO_DIR/.git/future-commit"

    # HOME override isolates from user's global config
    (cd "$DEMO_DIR" && HOME="$DEMO_DIR" vhs "$TAPE_FILE")

    # Move output GIF to assets
    mv "$DEMO_DIR/${tape}.gif" "$ASSETS_DIR/${tape}.gif"

    echo "  Done: assets/${tape}.gif"
    echo ""
done

echo "All GIFs generated in $ASSETS_DIR/"
ls -lh "$ASSETS_DIR"/*.gif
