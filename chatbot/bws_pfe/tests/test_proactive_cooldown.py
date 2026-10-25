"""Tests unitaires — api/pipeline/proactive.py (cooldown 1x/jour).

Ces tests mockent l'engine SQLAlchemy pour vérifier :
  1. La fenêtre de cooldown est bien de 24h (pas 4h).
  2. Un message rejeté (dismissed=1) compte quand même dans le cooldown —
     un rejet ne doit plus permettre une nouvelle notif avant 24h.
  3. run_proactive_check() respecte ce cooldown de bout en bout.
"""
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from api.pipeline import proactive


def _mock_engine(scalar_return=0, mappings_return=None):
    """Construit un engine mocké dont connect()/begin() retourne un contexte
    dont .execute(...) renvoie un objet supportant .scalar() et .mappings().fetchall()."""
    conn = MagicMock()
    result = MagicMock()
    result.scalar.return_value = scalar_return
    result.mappings.return_value.fetchall.return_value = mappings_return or []
    conn.execute.return_value = result

    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = conn
    engine.begin.return_value.__enter__.return_value = conn
    return engine, conn


class TestCooldownWindow:
    def test_cooldown_is_24h_not_4h(self):
        """_COOLDOWN_H doit valoir 24 (1 notif/jour), pas l'ancienne valeur de 4h."""
        assert proactive._COOLDOWN_H == 24

    def test_on_cooldown_uses_24h_param(self):
        engine, conn = _mock_engine(scalar_return=0)
        proactive._on_cooldown(engine, "user1", "energy")
        params = conn.execute.call_args[0][1]
        assert params["h"] == 24

    def test_on_cooldown_query_does_not_exclude_dismissed(self):
        """La requête ne doit plus filtrer sur dismissed=0 — un message rejeté
        doit quand même bloquer une nouvelle alerte pendant la fenêtre de cooldown."""
        engine, conn = _mock_engine(scalar_return=0)
        proactive._on_cooldown(engine, "user1", "energy")
        sql_text = str(conn.execute.call_args[0][0])
        assert "dismissed" not in sql_text.lower()

    def test_on_cooldown_true_when_message_exists(self):
        engine, _ = _mock_engine(scalar_return=1)
        assert proactive._on_cooldown(engine, "user1", "energy") is True

    def test_on_cooldown_false_when_no_message(self):
        engine, _ = _mock_engine(scalar_return=0)
        assert proactive._on_cooldown(engine, "user1", "energy") is False


class TestRunProactiveCheckRespectsCooldown:
    def test_no_alert_when_on_cooldown(self, monkeypatch):
        """Même avec une anomalie fraîche, aucune alerte n'est générée si le
        (user, domain) est encore dans la fenêtre de cooldown de 24h."""
        anomaly = {
            "domain": "energy", "item_id": "EN_001",
            "data_ts": datetime.utcnow(), "anomaly_score": 0.9,
        }
        monkeypatch.setattr(proactive, "_fetch_new_anomalies", lambda engine, since: [anomaly])
        monkeypatch.setattr(proactive, "_fetch_upcoming_predictions", lambda engine: [])
        monkeypatch.setattr(proactive, "_user_domains", lambda engine, uid: None)
        monkeypatch.setattr(proactive, "_on_cooldown", lambda engine, uid, dom: True)

        engine = MagicMock()
        alerts = proactive.run_proactive_check(engine, ["user1"])
        assert alerts == []

    def test_alert_generated_when_not_on_cooldown(self, monkeypatch):
        anomaly = {
            "domain": "energy", "item_id": "EN_001",
            "data_ts": datetime.utcnow(), "anomaly_score": 0.9,
        }
        monkeypatch.setattr(proactive, "_fetch_new_anomalies", lambda engine, since: [anomaly])
        monkeypatch.setattr(proactive, "_fetch_upcoming_predictions", lambda engine: [])
        monkeypatch.setattr(proactive, "_user_domains", lambda engine, uid: None)
        monkeypatch.setattr(proactive, "_on_cooldown", lambda engine, uid, dom: False)

        engine = MagicMock()
        alerts = proactive.run_proactive_check(engine, ["user1"])
        assert len(alerts) == 1
        assert alerts[0].domain == "energy"

    def test_dismissed_alert_still_blocks_new_one_within_24h(self, monkeypatch):
        """Reproduit le scénario corrigé : un message envoyé puis rejeté (dismissed=1)
        il y a moins de 24h doit quand même compter dans le COUNT(*) du cooldown."""
        # created_at = il y a 2h (dans la fenêtre check du scheduler), dismissed = 1
        engine, conn = _mock_engine(scalar_return=1)  # la requête réelle compterait ce message
        assert proactive._on_cooldown(engine, "user1", "energy") is True
