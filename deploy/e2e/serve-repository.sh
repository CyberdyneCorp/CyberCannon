#!/bin/sh
# The source of truth, served read-only over the git protocol.
#
# Git is the source of truth, so the end-to-end stack contains a real repository
# rather than a stub: the working copy the API keeps is a real clone of it, and
# a read really is served from a git object database at a pinned revision.
set -eu

# `git daemon` is not part of Alpine's `git` package — it is the separate
# `git-daemon` package, and `alpine/git` installs `git git-lfs tig gpg less
# openssh patch perl` and not that one. Without this line the entry point exits
# immediately with *"git: 'daemon' is not a git command"*, the health check
# never passes, and `docker compose up --wait` fails before the api is ever
# started, because the api waits on this service being healthy.
apk add --no-cache git-daemon

mkdir -p /srv/git/ronin
cp -R /seed/ronin/. /srv/git/ronin/
cd /srv/git/ronin

git config --global user.email "e2e@cybercanon.invalid"
git config --global user.name "CyberCanon end-to-end"
git config --global init.defaultBranch main
git init --quiet
git add --all
git commit --quiet --message "The worked example, as the end-to-end stack finds it"

exec git daemon \
    --verbose \
    --reuseaddr \
    --export-all \
    --base-path=/srv/git \
    --listen=0.0.0.0 \
    /srv/git
