#!/bin/sh
# Install the repository's git hooks (F-461): sets core.hooksPath to ops/hooks so every push
# from any worktree of this repository runs ops/hooks/pre-push, which refuses an unproven
# push to the production branch. Idempotent; changes only this repository's git config.
set -eu
top=$(git rev-parse --show-toplevel)
chmod +x "$top/ops/hooks/pre-push"
git -C "$top" config core.hooksPath ops/hooks
echo "core.hooksPath=$(git -C "$top" config --get core.hooksPath)"
