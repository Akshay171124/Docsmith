# Configs

Layered YAML configuration, resolved in priority order (later wins):

1. `base.yaml` — defaults shipped with Docsmith.
2. A repo's own `.docsmith.yml` (optional) — per-project overrides.
3. GitHub Action `with:` inputs (see `action.yml`) — highest priority.

`src/utils/config.py` performs the merge. Keep `base.yaml` as the single source of
default values; never duplicate defaults into code.
