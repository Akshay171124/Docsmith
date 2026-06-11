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

## Planned per-component docs
- `parsing.md` — tree-sitter queries, language config, doc-section model
- `index.md` — index schema, persistence, incremental update
- `detection.md` — diff→symbol mapping, linking, triage rules
- `repair.md` — repair/validation prompts, confidence routing
- `github.md` — reporter behavior, PR/comment formats
