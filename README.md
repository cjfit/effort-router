# effort-router

**Never set `/effort` by hand again.** effort-router classifies every request and dials Claude Code's reasoning effort to match, turn by turn: low for a typo fix, max for security-sensitive work. It logs token usage as it goes, so you can see exactly what it saved and what it misrouted.

## Problem
- Effort is a session-wide setting; there is no programmatic way to change it mid-conversation.
- A high default wastes tokens on trivial edits; a low default underthinks hard problems.

## How it works
- Ships five tiny skills, one per effort tier. A skill's frontmatter `effort` override applies for the rest of the turn.
- Tiers: low (typos, renames), medium (single-file additions, known-cause fixes), high (multi-file features, refactors, unknown-cause debugging), xhigh (architecture, concurrency bugs, migrations), max (anything security-sensitive, retries after a failure, explicit think-hard requests).
- Two hooks enforce the routing: `SessionStart` injects a standing "classify every request" instruction, and `UserPromptSubmit` re-anchors it on every prompt (~20 tokens) so it survives long, resumed, or compacted sessions.
- Skill frontmatter `model` overrides are ignored at runtime (claude-code#45191), so the plugin routes effort only.

## Token tracking
- A `Stop` hook logs each completed turn (tier, model, output tokens) to `~/.claude/effort-router/usage/<session_id>.jsonl`, refreshed after every turn.
- The `effort-report` skill estimates tokens saved by downshifting and flags likely misroutes: low/medium turns that ballooned, and high/xhigh/max turns that stayed tiny.
- It also breaks usage down by tier, day, model, and session.

## What the effort report tells you

A real report after three days of use:

```
== savings from downshifting ==
  36,503 output tokens saved across 6 low-routed turns

== context ==
tier        turns  output tokens  mean/turn
low             6           5222        870
medium          8          55633       6954
high           13         274807      21139
xhigh           4         127644      31911
unrouted       36         657742      18271
```

Three things it makes visible:

- **Whether routing pays for itself.** Mean output per turn here ranges from 870 tokens at low to 31,911 at xhigh — a ~35x spread. The savings line estimates what the 6 low-routed turns would have cost at the medium-tier mean. It's a counterfactual, so treat it as directional, not accounting.
- **Misroutes worth a look.** The flags are token-size heuristics, not verdicts. Above, one medium-routed turn burned 36,578 tokens — a multi-repo task that should have routed high; it likely flailed for lack of reasoning. The "overrouted" high turns were tiny, but a small turn at high effort can also be a hard question with a short answer.
- **Whether routing is happening at all.** Here `unrouted` dominates (36 of 67 turns) because sessions that predate the plugin install keep their old hooks until restarted. A high unrouted share after installation means the nudge isn't firing — restart those sessions.

## Latency
- The main cost is the routing itself: one extra `effort-*` skill invocation at the start of each turn, i.e. one additional model round trip before real work begins (typically ~1-3 seconds).
- Routing runs once per user prompt, not on every model step: a turn's intermediate tool calls and responses are unaffected. Classification only happens when the model gets new human input.
- The hooks are local scripts and add effectively nothing: `SessionStart` and `UserPromptSubmit` echo a static instruction (milliseconds, 5 s timeout), and the `Stop` logging hook runs after the response is already delivered.
- Downshifted turns usually win the time back: low effort on a trivial task spends far less time reasoning than a high-effort default would.

## Caveats
- Overrides last one turn; every turn re-classifies from scratch.
- The per-prompt nudge costs ~20 tokens, and each one stays in the transcript.
- Available tiers depend on the session's model (Opus 4.6 and Sonnet 4.6 lack `xhigh`, for example).
- The override is invisible in the UI: the `/effort` menu still shows the session setting. Proof of routing is the `effort-*` skill invocation at the start of the turn.
- Sessions already running when you install won't log usage until restarted.
