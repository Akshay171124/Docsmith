"""Stage 5: LLM staleness investigator with read_file/grep tools; confirms staleness + diagnosis."""

from __future__ import annotations

from src.detection.models import FileChange, InvestigationInput, Suspect
from src.models import Index
from src.parsing.code_parser import parse_source
from src.parsing.languages import language_for_path


def build_investigation_inputs(
    suspects: list[Suspect],
    file_changes: list[FileChange],
    index: Index,
) -> list[InvestigationInput]:
    """Assemble per-suspect investigation inputs from detection output.

    Args:
        suspects: Candidate symbol-to-doc-section links surfaced by detection.
        file_changes: The diffs the suspects were derived from.
        index: The current index, used to resolve doc section text.

    Returns:
        One `InvestigationInput` per unique `(symbol_id, section_id)` pair, in the
        order suspects were first seen. Suspects whose section is missing from the
        index are skipped.
    """
    by_path = {fc.path: fc for fc in file_changes}
    seen: set[tuple[str, str]] = set()
    inputs: list[InvestigationInput] = []

    for suspect in suspects:
        key = (suspect.symbol_id, suspect.section_id)
        if key in seen:
            continue

        section = index.sections.get(suspect.section_id)
        if section is None:
            continue
        seen.add(key)

        file, qualified_name = suspect.symbol_id.split("::", 1)
        symbol_name = qualified_name.rsplit(".", 1)[-1]

        fc = by_path.get(file)
        old_code = _extract_source(fc.old_content if fc else None, file, qualified_name)
        new_code = _extract_source(fc.new_content if fc else None, file, qualified_name)

        inputs.append(
            InvestigationInput(
                symbol_id=suspect.symbol_id,
                section_id=suspect.section_id,
                change_kind=suspect.change_kind,
                symbol_name=symbol_name,
                old_code=old_code,
                new_code=new_code,
                doc_section_text=section.raw,
            )
        )

    return inputs


def _extract_source(content: str | None, file: str, qualified_name: str) -> str | None:
    """Extract a symbol's source text from full file content by re-parsing.

    Args:
        content: Full file content, or None if the file didn't exist at this revision.
        file: Repo-relative path of the file (used to resolve the language).
        qualified_name: Fully qualified name of the symbol to extract.

    Returns:
        The symbol's source lines (1-based, inclusive), or None if `content` is
        None, the language is unsupported, or the symbol isn't found.
    """
    if content is None:
        return None

    language = language_for_path(file)
    if language is None:
        return None

    symbols = parse_source(content, file, language)
    symbol = next((s for s in symbols if s.qualified_name == qualified_name), None)
    if symbol is None:
        return None

    lines = content.splitlines()
    return "\n".join(lines[symbol.start_line - 1 : symbol.end_line])
