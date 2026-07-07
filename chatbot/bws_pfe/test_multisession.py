"""
Test de l'architecture multi-sessions.
Lance le serveur d'abord : python aria_api.py
Puis exécute : python test_multisession.py
"""

import asyncio
import httpx

BASE = 'http://localhost:8001'

CLIENTS = [
    {'sessionId': 'aaa', 'userId': 'client_A', 'question': 'Bonjour, quelle est la température actuelle ?'},
    {'sessionId': 'bbb', 'userId': 'client_B', 'question': 'Bonjour, y a-t-il des alertes actives ?'},
    {'sessionId': 'ccc', 'userId': 'client_C', 'question': 'Bonjour, montre-moi la consommation eau.'},
]


async def send_message(client: httpx.AsyncClient, payload: dict, label: str) -> dict:
    print(f'\n[{label}] Envoi : {payload["question"]}')
    resp = await client.post(f'{BASE}/chat', json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    print(f'[{label}] session_id={data["session_id"]}  thread_id={data["thread_id"]}')
    print(f'[{label}] Réponse ({data["confidence"]}) : {data["answer"][:120]}...')
    return data


async def get_sessions(client: httpx.AsyncClient):
    resp = await client.get(f'{BASE}/sessions')
    resp.raise_for_status()
    sessions = resp.json()
    print(f'\n[EMPLOYE] Sessions actives ({len(sessions)}) :')
    for s in sessions:
        print(f'  • {s["session_id"]:6s}  user={s["user_id"]:12s}  thread={s["thread_id"]}')
    return sessions


async def get_session_messages(client: httpx.AsyncClient, session_id: str):
    resp = await client.get(f'{BASE}/sessions/{session_id}/messages')
    resp.raise_for_status()
    data = resp.json()
    print(f'\n[EMPLOYE] Conversation session "{session_id}" ({len(data["messages"])} msg) :')
    for m in data['messages']:
        role = 'Client  ' if m['role'] == 'user' else 'ARIA    '
        print(f'  [{role}] {m["content"][:100]}')


async def test_continue_session(client: httpx.AsyncClient):
    """Vérifier qu'une session reprend son historique."""
    print('\n' + '='*60)
    print('TEST : reprise de session (session aaa envoie 2ème message)')
    await send_message(client, {
        'sessionId': 'aaa',
        'userId': 'client_A',
        'question': 'Et l\'humidité ?',
    }, 'aaa-msg2')


async def main():
    print('=' * 60)
    print('TEST MULTI-SESSIONS ARIA')
    print('=' * 60)

    async with httpx.AsyncClient() as client:
        # 1. Vérifier que l'API est prête
        health = await client.get(f'{BASE}/health')
        if health.status_code != 200:
            print('ERREUR : serveur non disponible. Lancez aria_api.py d\'abord.')
            return
        print(f'Serveur OK : {health.json()}')

        # 2. Trois clients envoient des messages en parallèle
        print('\n' + '-'*60)
        print('ÉTAPE 1 : 3 clients simultanés (sessions aaa, bbb, ccc)')
        print('-'*60)
        tasks = [
            send_message(client, c, c['sessionId'])
            for c in CLIENTS
        ]
        await asyncio.gather(*tasks)

        # 3. Vue employé : liste des sessions
        print('\n' + '-'*60)
        print('ÉTAPE 2 : Vue employé — sessions actives')
        print('-'*60)
        await get_sessions(client)

        # 4. Employé consulte la conversation de "aaa"
        print('\n' + '-'*60)
        print('ÉTAPE 3 : Employé consulte la session "aaa"')
        print('-'*60)
        await get_session_messages(client, 'aaa')

        # 5. Session aaa envoie un 2ème message (test continuité)
        print('\n' + '-'*60)
        print('ÉTAPE 4 : Continuité de session')
        print('-'*60)
        await test_continue_session(client)

        # 6. Sessions toujours distinctes
        print('\n' + '-'*60)
        print('ÉTAPE 5 : Vérification isolation des sessions')
        print('-'*60)
        sessions = await get_sessions(client)
        thread_ids = [s['thread_id'] for s in sessions]
        if len(set(thread_ids)) == len(thread_ids):
            print('\n[OK] Toutes les sessions ont des thread_id distincts — isolation confirmée.')
        else:
            print('\n[ERREUR] Des sessions partagent le même thread_id !')


if __name__ == '__main__':
    asyncio.run(main())
