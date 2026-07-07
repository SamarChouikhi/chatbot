"""Tests unitaires — api/models.py (validation Pydantic)"""
import pytest
from pydantic import ValidationError

from api.models import (
    AVAILABLE_MODULES,
    EmployeeCreate,
    EmployeeUpdate,
    ChatRequest,
    ChatResponse,
    FeedbackRequest,
    ThreadInfo,
    MessageOut,
    QuickReply,
)


# ── AVAILABLE_MODULES ─────────────────────────────────────────────────────────

def test_available_modules_not_empty():
    assert len(AVAILABLE_MODULES) > 0

def test_available_modules_contains_expected():
    assert "eau" in AVAILABLE_MODULES
    assert "alertes" in AVAILABLE_MODULES


# ── EmployeeCreate ────────────────────────────────────────────────────────────

class TestEmployeeCreate:
    def test_valid_minimal(self):
        e = EmployeeCreate(user_id="u1", name="Alice")
        assert e.user_id == "u1"
        assert e.is_admin is False
        assert e.allowed_modules == []

    def test_valid_with_modules(self):
        e = EmployeeCreate(user_id="u2", name="Bob", allowed_modules=["eau", "gaz"])
        assert "eau" in e.allowed_modules

    def test_admin_flag(self):
        e = EmployeeCreate(user_id="u3", name="Admin", is_admin=True)
        assert e.is_admin is True

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            EmployeeCreate(name="No ID")

    def test_missing_name(self):
        with pytest.raises(ValidationError):
            EmployeeCreate(user_id="u4")


# ── EmployeeUpdate ────────────────────────────────────────────────────────────

class TestEmployeeUpdate:
    def test_all_optional_empty(self):
        u = EmployeeUpdate()
        assert u.name is None
        assert u.allowed_modules is None
        assert u.is_admin is None

    def test_partial_update(self):
        u = EmployeeUpdate(name="Nouveau nom")
        assert u.name == "Nouveau nom"
        assert u.is_admin is None


# ── ChatRequest ───────────────────────────────────────────────────────────────

class TestChatRequest:
    def test_minimal_valid(self):
        r = ChatRequest(question="Quelle est la température ?")
        assert r.question == "Quelle est la température ?"
        assert r.userId == "default_user"
        assert r.lang == "fr"

    def test_with_all_fields(self):
        r = ChatRequest(
            question="Test",
            sessionId="sess-1",
            threadId="th-1",
            userId="user-42",
            allowed_modules=["eau"],
            lang="en",
        )
        assert r.sessionId == "sess-1"
        assert r.lang == "en"

    def test_missing_question_raises(self):
        with pytest.raises(ValidationError):
            ChatRequest()

    def test_threadid_retrocompat(self):
        r = ChatRequest(question="Hello", threadId="old-thread")
        assert r.threadId == "old-thread"


# ── ChatResponse ──────────────────────────────────────────────────────────────

class TestChatResponse:
    def test_minimal_valid(self):
        r = ChatResponse(
            answer="La temp est 22°C",
            backend="ollama",
            level="data",
            duration=1.23,
            thread_id="th-abc",
        )
        assert r.answer == "La temp est 22°C"
        assert r.quick_replies is None
        assert r.confidence is None

    def test_with_quick_replies(self):
        r = ChatResponse(
            answer="Choisissez une option",
            backend="groq",
            level="static",
            duration=0.5,
            thread_id="th-xyz",
            quick_replies=[QuickReply(label="Eau", value="eau")],
        )
        assert len(r.quick_replies) == 1
        assert r.quick_replies[0].label == "Eau"

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            ChatResponse(answer="ok")


# ── FeedbackRequest ───────────────────────────────────────────────────────────

class TestFeedbackRequest:
    def test_valid_upvote(self):
        f = FeedbackRequest(message_id=1, thread_id="th-1", vote="up")
        assert f.vote == "up"
        assert f.user_id == "default_user"

    def test_valid_downvote_with_comment(self):
        f = FeedbackRequest(
            message_id=2, thread_id="th-2",
            vote="down", comment="Réponse incorrecte", user_id="alice"
        )
        assert f.comment == "Réponse incorrecte"

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            FeedbackRequest(vote="up")


# ── ThreadInfo ────────────────────────────────────────────────────────────────

class TestThreadInfo:
    def test_valid(self):
        t = ThreadInfo(
            thread_id="th-1",
            title="Discussion eau",
            message_count=5,
            created_at="2025-01-01T10:00:00",
            updated_at="2025-01-01T11:00:00",
        )
        assert t.is_favorite is False
        assert t.preview is None

    def test_with_preview_and_favorite(self):
        t = ThreadInfo(
            thread_id="th-2",
            title="Énergie",
            message_count=2,
            created_at="2025-01-01",
            updated_at="2025-01-01",
            preview="Consommation en kWh",
            is_favorite=True,
        )
        assert t.is_favorite is True


# ── MessageOut ────────────────────────────────────────────────────────────────

class TestMessageOut:
    def test_minimal_valid(self):
        m = MessageOut(role="user", content="Bonjour", created_at="2025-01-01T10:00:00")
        assert m.id is None
        assert m.feedback is None

    def test_with_all_fields(self):
        m = MessageOut(
            id=42,
            role="assistant",
            content="Réponse",
            level="data",
            backend="ollama",
            created_at="2025-01-01",
            feedback="up",
        )
        assert m.id == 42
        assert m.feedback == "up"
