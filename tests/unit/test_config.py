"""Unit tests for src/utils/config.py — minimal config loader."""

from __future__ import annotations

from src.utils.config import load_settings


class TestLoadSettingsFromBaseYaml:
    """Tests against the real configs/base.yaml."""

    def test_ignore_paths_contains_test_glob(self):
        s = load_settings()
        assert "**/test_*.py" in s.ignore_paths

    def test_skip_comment_only_is_true(self):
        s = load_settings()
        assert s.skip_comment_only is True

    def test_skip_whitespace_only_is_true(self):
        s = load_settings()
        assert s.skip_whitespace_only is True

    def test_doc_ignore_contains_changelog(self):
        s = load_settings()
        assert "**/CHANGELOG.md" in s.doc_ignore


class TestLoadSettingsMissingKeys:
    """Tests against a minimal YAML that has neither triage nor docs sections."""

    def test_defaults_when_sections_absent(self, tmp_path):
        minimal = tmp_path / "minimal.yaml"
        minimal.write_text("linking: {}\n")
        s = load_settings(path=str(minimal))
        assert s.ignore_paths == []
        assert s.doc_ignore == []
        assert s.skip_comment_only is True
        assert s.skip_whitespace_only is True

    def test_does_not_raise_on_missing_sections(self, tmp_path):
        minimal = tmp_path / "minimal.yaml"
        minimal.write_text("linking: {}\n")
        # Should not raise
        load_settings(path=str(minimal))

    def test_null_values_default_to_empty_and_true(self, tmp_path):
        null_yaml = tmp_path / "null_values.yaml"
        null_yaml.write_text(
            "triage:\n"
            "  ignore_paths:\n"
            "  skip_comment_only:\n"
            "  skip_whitespace_only:\n"
            "docs:\n"
            "  ignore:\n"
        )
        s = load_settings(path=str(null_yaml))
        assert s.ignore_paths == []
        assert s.doc_ignore == []
        assert s.skip_comment_only is True
        assert s.skip_whitespace_only is True

    def test_explicit_false_is_preserved(self, tmp_path):
        false_yaml = tmp_path / "false_values.yaml"
        false_yaml.write_text("triage:\n  skip_comment_only: false\n")
        s = load_settings(path=str(false_yaml))
        assert s.skip_comment_only is False


class TestLoadSettingsOverrides:
    """Tests for the overrides parameter."""

    def test_override_skip_comment_only(self):
        s = load_settings(overrides={"skip_comment_only": False})
        assert s.skip_comment_only is False

    def test_override_does_not_affect_other_fields(self):
        s = load_settings(overrides={"skip_comment_only": False})
        assert s.skip_whitespace_only is True
        assert "**/test_*.py" in s.ignore_paths

    def test_override_llm_backend(self):
        s = load_settings(overrides={"llm_backend": "fake"})
        assert s.llm_backend == "fake"


class TestLoadSettingsLlmFromBaseYaml:
    """Tests against the real configs/base.yaml llm: block."""

    def test_llm_backend_is_ollama(self):
        s = load_settings()
        assert s.llm_backend == "ollama"

    def test_ollama_model(self):
        s = load_settings()
        assert s.ollama_model == "qwen2.5-coder:7b"

    def test_ollama_host(self):
        s = load_settings()
        assert s.ollama_host == "http://localhost:11434"

    def test_claude_model(self):
        s = load_settings()
        assert s.claude_model == "claude-sonnet-5"


class TestLoadSettingsLlmMissingSection:
    """Tests for the llm: section being absent entirely."""

    def test_defaults_when_llm_section_absent(self, tmp_path):
        minimal = tmp_path / "minimal.yaml"
        minimal.write_text("linking: {}\n")
        s = load_settings(path=str(minimal))
        assert s.llm_backend == "ollama"
        assert s.ollama_model == "qwen2.5-coder:7b"
        assert s.ollama_host == "http://localhost:11434"
        assert s.claude_model == "claude-sonnet-5"


def test_load_settings_reads_repair_block(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(
        "repair:\n"
        "  confidence_threshold: 0.6\n"
        "  autofix_change_kinds: [signature_changed, body_changed]\n"
    )
    s = load_settings(str(cfg))
    assert s.repair_confidence_threshold == 0.6
    assert s.repair_autofix_change_kinds == ("signature_changed", "body_changed")


def test_load_settings_repair_defaults(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("{}\n")
    s = load_settings(str(cfg))
    assert s.repair_confidence_threshold == 0.8
    assert s.repair_autofix_change_kinds == ("signature_changed",)
