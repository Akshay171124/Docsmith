# Curated evaluation corpus

Each `*.json` file in this directory is one hand-authored replay case, loaded by
`evaluation.corpus.load_curated_cases()`. A case has four top-level keys:

- `case_id` (str): unique identifier for the case.
- `base_files` (`{path: content}`): repo-relative file contents before the change.
- `head_files` (`{path: content}`): repo-relative file contents after the change.
- `gold` (object): ground truth for scoring, with two keys:
  - `stale_section_ids` (`[str]`): doc section ids that SHOULD be flagged stale.
    Empty means this is a negative case (no doc drift expected).
  - `fixes` (`{section_id: text}`): expected corrected text per section, when
    the case also evaluates repair quality (may be `{}` for detection-only cases).

## Section id scheme

Doc sections are identified as `"<file>#<heading-slug>"`, where the slug is the
heading text lowercased with runs of non-alphanumeric characters collapsed to a
single hyphen. For example, a `## Users` heading in `README.md` has section id
`README.md#users`, and `## Totals` maps to `README.md#totals`.

## Bare-name rule (load-bearing)

When a doc section references a code symbol in backticks, it must use the BARE
symbol name — e.g. `` `create_user` ``, not `` `create_user(name)` ``. The doc
parser's identifier regex only matches inline-code tokens that are valid
identifiers (`^[A-Za-z_][A-Za-z0-9_]*$`); a token containing parentheses does not
match, so a parenthesized reference silently fails to link the doc section to the
symbol. Any new case added to this corpus must follow this rule or its expected
detection behavior will not hold.

## Adding a case

Add both a positive (non-empty `stale_section_ids`) and, where useful, a negative
(empty `stale_section_ids`) example for the change pattern you're covering, so the
corpus keeps measuring both recall and precision.
