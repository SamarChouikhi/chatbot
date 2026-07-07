"""Tests unitaires — api/pipeline/proactive_broadcaster.py

ProactiveBroadcaster est une classe pure Python (asyncio.Queue, defaultdict).
Aucune dépendance DB ou réseau — testable sans mock.
"""
import asyncio
import pytest

from api.pipeline.proactive_broadcaster import ProactiveBroadcaster


@pytest.fixture
def broadcaster() -> ProactiveBroadcaster:
    return ProactiveBroadcaster()


# ── register() ────────────────────────────────────────────────────────────────

class TestRegister:
    def test_register_returns_queue(self, broadcaster):
        q = broadcaster.register("user1")
        assert isinstance(q, asyncio.Queue)

    def test_register_increments_connection_count(self, broadcaster):
        broadcaster.register("user1")
        assert broadcaster.connection_count() == 1

    def test_two_tabs_same_user(self, broadcaster):
        broadcaster.register("user1")
        broadcaster.register("user1")
        assert broadcaster.connection_count() == 2

    def test_two_different_users(self, broadcaster):
        broadcaster.register("alice")
        broadcaster.register("bob")
        assert broadcaster.connection_count() == 2

    def test_queue_has_correct_maxsize(self, broadcaster):
        q = broadcaster.register("user1")
        assert q.maxsize == 50


# ── unregister() ─────────────────────────────────────────────────────────────

class TestUnregister:
    def test_unregister_removes_queue(self, broadcaster):
        q = broadcaster.register("user1")
        broadcaster.unregister("user1", q)
        assert broadcaster.connection_count() == 0

    def test_unregister_cleans_empty_user_entry(self, broadcaster):
        q = broadcaster.register("user1")
        broadcaster.unregister("user1", q)
        assert "user1" not in broadcaster.active_user_ids()

    def test_unregister_unknown_user_safe(self, broadcaster):
        fake_q = asyncio.Queue()
        broadcaster.unregister("ghost", fake_q)   # ne lève pas d'exception

    def test_unregister_one_of_two_tabs(self, broadcaster):
        q1 = broadcaster.register("user1")
        q2 = broadcaster.register("user1")
        broadcaster.unregister("user1", q1)
        assert broadcaster.connection_count() == 1
        assert "user1" in broadcaster.active_user_ids()

    def test_unregister_unknown_queue_safe(self, broadcaster):
        broadcaster.register("user1")
        fake_q = asyncio.Queue()
        broadcaster.unregister("user1", fake_q)   # queue pas dans la liste
        assert broadcaster.connection_count() == 1


# ── push() ────────────────────────────────────────────────────────────────────

class TestPush:
    def test_push_delivers_to_single_queue(self, broadcaster):
        q = broadcaster.register("user1")
        payload = {"domain": "energy", "message": "anomalie détectée"}
        broadcaster.push("user1", payload)
        assert not q.empty()
        assert q.get_nowait() == payload

    def test_push_delivers_to_all_queues_of_user(self, broadcaster):
        q1 = broadcaster.register("user1")
        q2 = broadcaster.register("user1")
        broadcaster.push("user1", {"msg": "test"})
        assert not q1.empty()
        assert not q2.empty()

    def test_push_does_not_affect_other_users(self, broadcaster):
        broadcaster.register("alice")
        q_bob = broadcaster.register("bob")
        broadcaster.push("alice", {"msg": "pour alice"})
        assert q_bob.empty()

    def test_push_to_nonexistent_user_safe(self, broadcaster):
        broadcaster.push("nobody", {"msg": "perdu"})   # ne lève pas

    def test_full_queue_does_not_raise(self, broadcaster):
        q = broadcaster.register("user1")
        payload = {"x": 1}
        # Remplir la queue à ras bord (maxsize=50)
        for _ in range(50):
            q.put_nowait(payload)
        # Le 51e appel doit être absorbé silencieusement
        broadcaster.push("user1", payload)   # QueueFull loggé mais pas levé


# ── active_user_ids() / connection_count() ───────────────────────────────────

class TestQueryMethods:
    def test_empty_broadcaster_has_no_users(self, broadcaster):
        assert broadcaster.active_user_ids() == []
        assert broadcaster.connection_count() == 0

    def test_active_user_ids_lists_registered_users(self, broadcaster):
        broadcaster.register("alice")
        broadcaster.register("bob")
        ids = broadcaster.active_user_ids()
        assert "alice" in ids
        assert "bob" in ids

    def test_connection_count_sums_all_connections(self, broadcaster):
        broadcaster.register("u1")
        broadcaster.register("u1")
        broadcaster.register("u2")
        assert broadcaster.connection_count() == 3

    def test_user_removed_from_active_after_full_unregister(self, broadcaster):
        q = broadcaster.register("solo")
        broadcaster.unregister("solo", q)
        assert "solo" not in broadcaster.active_user_ids()
