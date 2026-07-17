#!/usr/bin/env bash
# SessionStart hook for effort-router (fires on startup and /clear only).
# The effort-* skills add no new capability, so Claude rarely consults them
# on its own — this instruction makes the routing happen. Effort overrides
# last one turn, so the classification must be repeated for every request.

cat <<'EOF'
[effort-router] For EVERY user request in this session, before starting the
work, classify the task's complexity and invoke exactly one matching skill:

  - effort-low    trivial/mechanical: typos, renames, one-liners, formatting
  - effort-medium routine, well-scoped: single-file changes, known-cause fixes
  - effort-high   substantial: multi-file features, unknown-cause debugging, refactors
  - effort-xhigh  very hard: architecture, gnarly concurrency bugs, migrations
  - effort-max    most expensive to get wrong: anything security-sensitive,
                  retries after a failed attempt, explicit think-hard requests

The skill's frontmatter sets the reasoning effort for the rest of the turn —
the override only works if the skill is invoked.
Re-classify on every request; the previous turn's tier does not carry over.
This includes questions, reviews, and design discussions with no code
changes — advice is work too. Skip routing only for pure conversation with
no task at all (greetings, thanks).
EOF

exit 0
