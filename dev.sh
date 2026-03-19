#!/bin/bash
# Dev setup script for sparkrun
#
# Usage (must be sourced so the venv activates in your shell):
#   source dev.sh
#
# Quick start:
#   git clone https://github.com/scitrera/sparkrun.git -b develop
#   cd sparkrun
#   source dev.sh
#   sparkrun run --help

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

# Check for uv
if ! command -v uv &>/dev/null; then
    echo "Error: uv is not installed. Install it via: curl -LsSf https://astral.sh/uv/install.sh | sh"
    # Return instead of exit when sourced, exit when run directly
    return 1 2>/dev/null || exit 1
fi

# Create venv if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment at $VENV_DIR ..."
    uv venv "$VENV_DIR" --python 3.12
fi

# Activate the venv
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# Install in editable mode with dev extras
echo "Installing sparkrun in editable mode with dev dependencies ..."
uv pip install -e "$SCRIPT_DIR[dev]"

echo ""
echo "Done! sparkrun is ready to use in this shell."
echo "  sparkrun --help"
