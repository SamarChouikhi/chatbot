"""
In-memory SSE broadcaster pour les messages proactifs ARIA.

Un asyncio.Queue par connexion SSE (un utilisateur peut avoir plusieurs onglets).
broadcast(user_id, payload) pousse le payload dans toutes les queues actives de cet user.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

logger = logging.getLogger('aria.proactive.broadcaster')


class ProactiveBroadcaster:

    def __init__(self) -> None:
        # user_id → liste de queues (une par connexion SSE ouverte)
        self._queues: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def register(self, user_id: str) -> asyncio.Queue:
        """Crée une queue pour un client SSE. Appelé à l'ouverture de la connexion."""
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._queues[user_id].append(q)
        logger.debug('[BROADCASTER] +client user=%s connections=%d',
                     user_id, len(self._queues[user_id]))
        return q

    def unregister(self, user_id: str, queue: asyncio.Queue) -> None:
        """Supprime la queue. Appelé à la fermeture de la connexion SSE."""
        queues = self._queues.get(user_id, [])
        if queue in queues:
            queues.remove(queue)
        if not queues:
            self._queues.pop(user_id, None)
        logger.debug('[BROADCASTER] -client user=%s remaining=%d',
                     user_id, len(self._queues.get(user_id, [])))

    def push(self, user_id: str, payload: dict) -> None:
        """Pousse dans toutes les queues SSE actives pour cet utilisateur.
        Si la queue est pleine, évince le message le plus ancien pour insérer le nouveau."""
        for q in self._queues.get(user_id, []):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()   # évince le plus ancien
                    q.put_nowait(payload)
                    logger.warning('[BROADCASTER] queue pleine user=%s — message ancien évincé', user_id)
                except Exception:
                    logger.error('[BROADCASTER] impossible de délivrer le message user=%s', user_id)

    def active_user_ids(self) -> list[str]:
        """Liste des user_id ayant au moins une connexion SSE ouverte."""
        return list(self._queues.keys())

    def connection_count(self) -> int:
        return sum(len(qs) for qs in self._queues.values())


# Singleton — partagé entre scheduler.py et routes/proactive.py
_broadcaster = ProactiveBroadcaster()


def get_broadcaster() -> ProactiveBroadcaster:
    return _broadcaster
