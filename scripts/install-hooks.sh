#!/bin/sh
#
# Install the repo's git hooks into the active hooks directory.
# Safe to re-run. Run once after cloning:
#
#   sh scripts/install-hooks.sh
#
set -eu

repo_root=$(git rev-parse --show-toplevel)
hooks_dir=$(git rev-parse --git-path hooks)
src="$repo_root/scripts/git-hooks"

for hook in "$src"/*; do
	name=$(basename "$hook")
	dest="$hooks_dir/$name"
	cp "$hook" "$dest"
	chmod +x "$dest"
	echo "installed $name -> $dest"
done
