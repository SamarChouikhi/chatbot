"""Tests unitaires — mcp_client/llm_factory.py :: KeyStateManager

On teste la logique de rotation de clés API sans accès réseau ni fichier disque réel.
Le key_file est remplacé par un fichier temporaire (tmp_path fixture pytest).
"""
import json
import os
import pytest
from pathlib import Path

from mcp_client.llm_factory import KeyStateManager


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clear_keys(monkeypatch, prefix: str) -> None:
    """Supprime toutes les variables d'env pour un prefix donné (PREFIX, PREFIX_1..9)."""
    monkeypatch.delenv(prefix, raising=False)
    for i in range(1, 10):
        monkeypatch.delenv(f"{prefix}_{i}", raising=False)


# ── Fixture : state manager avec fichier temporaire ──────────────────────────

@pytest.fixture
def mgr(tmp_path) -> KeyStateManager:
    """KeyStateManager fresh avec un fichier d'état vide (tmp_path)."""
    return KeyStateManager(tmp_path / "key_state.json")


# ── collect_keys() ────────────────────────────────────────────────────────────

class TestCollectKeys:
    def test_no_env_returns_empty(self, monkeypatch):
        _clear_keys(monkeypatch, "GROQ_API_KEY")
        assert KeyStateManager.collect_keys("GROQ_API_KEY") == []

    def test_single_key_collected(self, monkeypatch):
        _clear_keys(monkeypatch, "GROQ_API_KEY")
        monkeypatch.setenv("GROQ_API_KEY", "sk-single")
        keys = KeyStateManager.collect_keys("GROQ_API_KEY")
        assert "sk-single" in keys

    def test_numbered_keys_collected_in_order(self, monkeypatch):
        _clear_keys(monkeypatch, "GROQ_API_KEY")
        monkeypatch.setenv("GROQ_API_KEY_1", "sk-one")
        monkeypatch.setenv("GROQ_API_KEY_2", "sk-two")
        keys = KeyStateManager.collect_keys("GROQ_API_KEY")
        assert keys[0] == "sk-one"
        assert keys[1] == "sk-two"

    def test_no_duplicates(self, monkeypatch):
        _clear_keys(monkeypatch, "GROQ_API_KEY")
        monkeypatch.setenv("GROQ_API_KEY_1", "sk-dup")
        monkeypatch.setenv("GROQ_API_KEY",   "sk-dup")
        keys = KeyStateManager.collect_keys("GROQ_API_KEY")
        assert keys.count("sk-dup") == 1

    def test_empty_env_value_ignored(self, monkeypatch):
        _clear_keys(monkeypatch, "GROQ_API_KEY")
        monkeypatch.setenv("GROQ_API_KEY_1", "")
        assert KeyStateManager.collect_keys("GROQ_API_KEY") == []

    def test_whitespace_key_ignored(self, monkeypatch):
        _clear_keys(monkeypatch, "GROQ_API_KEY")
        monkeypatch.setenv("GROQ_API_KEY_1", "   ")
        assert KeyStateManager.collect_keys("GROQ_API_KEY") == []


# ── Initialisation de l'état ──────────────────────────────────────────────────

class TestStateInit:
    def test_fresh_state_has_all_providers(self, mgr):
        for provider in ("groq", "gemini", "openrouter", "huggingface", "cerebras"):
            assert provider in mgr.state

    def test_fresh_state_current_is_zero(self, mgr):
        assert mgr.state["groq"]["current"] == 0
        assert mgr.state["gemini"]["current"] == 0

    def test_state_persisted_after_save(self, tmp_path):
        path = tmp_path / "ks.json"
        m = KeyStateManager(path)
        m.save()
        assert path.exists()
        loaded = json.loads(path.read_text())
        assert "groq" in loaded

    def test_corrupted_file_falls_back_to_defaults(self, tmp_path):
        path = tmp_path / "ks.json"
        path.write_text("{invalid json{{")
        m = KeyStateManager(path)
        assert "groq" in m.state   # état réinitialisé


# ── get_groq_key() ────────────────────────────────────────────────────────────

class TestGetGroqKey:
    def test_returns_first_available_key(self, mgr, monkeypatch):
        _clear_keys(monkeypatch, "GROQ_API_KEY")
        monkeypatch.setenv("GROQ_API_KEY_1", "sk-groq-1")
        key = mgr.get_groq_key("llama3")
        assert key == "sk-groq-1"

    def test_returns_none_when_no_keys(self, mgr, monkeypatch):
        _clear_keys(monkeypatch, "GROQ_API_KEY")
        assert mgr.get_groq_key("llama3") is None

    def test_skips_exhausted_key(self, mgr, monkeypatch):
        _clear_keys(monkeypatch, "GROQ_API_KEY")
        monkeypatch.setenv("GROQ_API_KEY_1", "sk-exhausted")
        monkeypatch.setenv("GROQ_API_KEY_2", "sk-fresh")
        mgr.mark_groq_exhausted("llama3", "sk-exhausted")
        key = mgr.get_groq_key("llama3")
        assert key == "sk-fresh"

    def test_returns_none_when_all_exhausted(self, mgr, monkeypatch):
        _clear_keys(monkeypatch, "GROQ_API_KEY")
        monkeypatch.setenv("GROQ_API_KEY_1", "sk-a")
        mgr.mark_groq_exhausted("llama3", "sk-a")
        assert mgr.get_groq_key("llama3") is None

    def test_exhaustion_is_model_specific(self, mgr, monkeypatch):
        _clear_keys(monkeypatch, "GROQ_API_KEY")
        monkeypatch.setenv("GROQ_API_KEY_1", "sk-only")
        mgr.mark_groq_exhausted("llama3", "sk-only")
        # La même clé est disponible pour un autre modèle
        key = mgr.get_groq_key("mixtral")
        assert key == "sk-only"


# ── mark_groq_exhausted() ─────────────────────────────────────────────────────

class TestMarkGroqExhausted:
    def test_marks_key_exhausted(self, mgr):
        mgr.mark_groq_exhausted("llama3", "sk-bad")
        assert "sk-bad" in mgr.state["groq"]["exhausted_llama3"]

    def test_no_duplicate_exhausted(self, mgr):
        mgr.mark_groq_exhausted("llama3", "sk-bad")
        mgr.mark_groq_exhausted("llama3", "sk-bad")
        assert mgr.state["groq"]["exhausted_llama3"].count("sk-bad") == 1


# ── get_gemini_key() / mark_gemini_exhausted() ────────────────────────────────

class TestGeminiKeyRotation:
    def test_returns_first_non_exhausted(self, mgr, monkeypatch):
        _clear_keys(monkeypatch, "GEMINI_API_KEY")
        monkeypatch.setenv("GEMINI_API_KEY_1", "gm-a")
        monkeypatch.setenv("GEMINI_API_KEY_2", "gm-b")
        mgr.mark_gemini_exhausted("gm-a")
        assert mgr.get_gemini_key() == "gm-b"

    def test_returns_none_all_exhausted(self, mgr, monkeypatch):
        _clear_keys(monkeypatch, "GEMINI_API_KEY")
        monkeypatch.setenv("GEMINI_API_KEY_1", "gm-x")
        mgr.mark_gemini_exhausted("gm-x")
        assert mgr.get_gemini_key() is None


# ── reset() ───────────────────────────────────────────────────────────────────

class TestReset:
    def test_reset_clears_exhausted(self, mgr):
        mgr.mark_gemini_exhausted("some-key")
        mgr.reset()
        assert mgr.state["gemini"].get("exhausted", []) == []

    def test_reset_sets_current_to_zero(self, mgr):
        mgr.state["groq"]["current"] = 5
        mgr.reset()
        assert mgr.state["groq"]["current"] == 0
