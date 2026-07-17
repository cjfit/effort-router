#!/usr/bin/env bash
# UserPromptSubmit hook for effort-router: a one-line per-turn nudge.
# The SessionStart instruction fades in long conversations and never fires
# on resume/compact, leaving most turns unrouted. Re-anchoring one line per
# prompt keeps routing alive; the full tier table isn't repeated because the
# tier boundaries live in the skill descriptions, always in context.

echo "[effort-router] Classify this request's complexity and invoke exactly one effort-* skill before starting work; skip only pure conversation with no task."

exit 0
