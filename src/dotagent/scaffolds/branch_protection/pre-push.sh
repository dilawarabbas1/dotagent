#!/usr/bin/env bash
# Installed by `dotagent git init-hooks` in the meta repo.
# Refuses to push when the staged contents violate the branch rules
# declared in `.agent/git.yaml`.
#
# To override (rare): `git push --no-verify`.

set -euo pipefail

remote="$1"
url="$2"

while read -r local_ref local_sha remote_ref remote_sha; do
    if [[ "$local_sha" == "0000000000000000000000000000000000000000" ]]; then
        continue   # branch deletion
    fi
    # branch name from remote_ref (refs/heads/<branch>)
    branch="${remote_ref#refs/heads/}"

    # Files in the push that this hook should check. Compare local commit
    # against remote (or empty if branch is new).
    if [[ "$remote_sha" == "0000000000000000000000000000000000000000" ]]; then
        # new branch — list all tracked files in the push
        files=$(git ls-tree -r --name-only "$local_sha" 2>/dev/null || true)
    else
        files=$(git diff --name-only "$remote_sha" "$local_sha" 2>/dev/null || true)
    fi

    if [[ -z "$files" ]]; then
        continue
    fi

    # Hand off to `dotagent git verify`. It will exit non-zero on violation.
    if ! echo "$files" | dotagent git verify --branch "$branch" --remote "$url" $(printf -- ' --paths %s' $files) >&2; then
        echo "" >&2
        echo "dotagent: push refused. Use 'git push --no-verify' to override (NOT recommended)." >&2
        exit 1
    fi
done
exit 0
