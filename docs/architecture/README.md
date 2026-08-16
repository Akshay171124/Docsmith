# Architecture

The authoritative design lives in
[`../superpowers/specs/2026-06-11-self-healing-docs-design.md`](../superpowers/specs/2026-06-11-self-healing-docs-design.md).
This folder holds per-component deep-dives as they are built (Forge keeps one doc per
component; we follow that).

## Data flow

```
PR event
   │
   ▼  [deterministic — no LLM]
diff_parser ─► symbol_mapper ─► candidate_linker ─► triage_filter
                                      ▲                    │
                                      │ query              │ surviving suspects
                                 ┌────┴─────┐              ▼
                                 │  INDEX   │      investigator (LLM + read/grep)
                                 │ symbols  │              │ confirmed-stale + diagnosis
                                 │ sections │              ▼
                                 │  links   │      repairer ─► validator ─► confidence_router
                                 │ embeds   │                                      │
                                 └──────────┘                          high ┌──────┴──────┐ low
                                                                            ▼             ▼
                                                                       fix-PR        inline flag
                                                                            └──────┬──────┘
                                                                                   ▼
                                                                            github/reporter
```

## Per-component references

Dedicated per-component docs (`parsing.md`, `index.md`, etc.) were never split out; the
authoritative per-sub-project references are the design specs and implementation plans under
[`docs/superpowers/specs/`](../superpowers/specs/) and
[`docs/superpowers/plans/`](../superpowers/plans/), with the living progress tracker in
[`docs/planning/roadmap.md`](../planning/roadmap.md). What each would have covered:

- **parsing** — tree-sitter queries, language config, doc-section model
- **index** — index schema, persistence, incremental update
- **detection** — diff→symbol mapping, linking, triage rules
- **repair** — repair/validation prompts, confidence routing
- **github** — reporter behavior, PR/comment formats
