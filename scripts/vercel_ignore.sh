#!/usr/bin/env bash
# Vercel "Ignored Build Step": exit 0 skips the deploy, exit 1 builds.
# Skip only when the previous deployed commit is available AND nothing outside
# docs/ownership files changed. .vercelignore strips .git before this runs on
# Vercel, so in practice this builds every push; it must never exit >1, which
# Vercel reports as a failed deployment.
if [ -n "${VERCEL_GIT_PREVIOUS_SHA:-}" ] && git rev-parse -q --verify "${VERCEL_GIT_PREVIOUS_SHA}^{commit}" >/dev/null 2>&1; then
  git diff --quiet "$VERCEL_GIT_PREVIOUS_SHA" HEAD -- . \
    ":(exclude)README.md" ":(exclude)LICENSE" ":(exclude).github/CODEOWNERS" ":(exclude).github/dependabot.yml"
  [ $? -eq 0 ] && exit 0
fi
exit 1
