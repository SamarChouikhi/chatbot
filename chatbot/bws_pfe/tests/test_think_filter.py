"""Tests unitaires — mcp_client/agent.py : _strip_think() et _ThinkStreamFilter.

Régression pour le bug : seul le chemin streaming (stream_process) filtrait les
blocs <think>…</think> émis par les modèles de raisonnement (ex. Groq
qwen/qwen3-32b, GROQ_MODEL_2 — atteint dès qu'une clé du modèle 1 est épuisée,
donc en usage normal, pas seulement en cas d'erreur). Le chemin non-streaming
(process()) et le "dernier recours" de stream_process() renvoyaient le contenu
brut, exposant le raisonnement interne du modèle à l'utilisateur final.
"""
from mcp_client.agent import _strip_think, _ThinkStreamFilter


class TestStripThink:
    def test_no_think_block_unchanged(self):
        assert _strip_think('La consommation est de 42 kWh.') == 'La consommation est de 42 kWh.'

    def test_removes_single_closed_block(self):
        text = '<think>je réfléchis à la question</think>La réponse est 42 kWh.'
        assert _strip_think(text) == 'La réponse est 42 kWh.'

    def test_removes_multiple_blocks(self):
        text = '<think>a</think>Début. <think>b</think>Fin.'
        assert _strip_think(text) == 'Début. Fin.'

    def test_removes_block_in_the_middle(self):
        text = 'Avant <think>raisonnement caché</think> après.'
        assert _strip_think(text) == 'Avant  après.'

    def test_unclosed_block_truncated_at_open_tag(self):
        """Réponse tronquée par un timeout en plein raisonnement : tout ce qui
        suit <think> (jamais fermé) doit disparaître plutôt que fuiter."""
        text = 'Voici les données : <think>je compare les seuils'
        assert _strip_think(text) == 'Voici les données :'

    def test_empty_string(self):
        assert _strip_think('') == ''

    def test_none_passthrough(self):
        assert _strip_think(None) is None

    def test_strips_surrounding_whitespace(self):
        text = '<think>x</think>   La réponse.   '
        assert _strip_think(text) == 'La réponse.'


class TestThinkStreamFilter:
    def test_passthrough_when_no_think_tags(self):
        f = _ThinkStreamFilter()
        out = f.feed('La consommation est de 42 kWh.')
        assert out == 'La consommation est de 42 kWh.'

    def test_strips_block_fed_in_one_call(self):
        f = _ThinkStreamFilter()
        out = f.feed('<think>raisonnement</think>Réponse finale.')
        assert out == 'Réponse finale.'

    def test_strips_block_split_across_multiple_feeds(self):
        """Les tokens LLM arrivent en petits morceaux — la balise <think> peut
        être coupée en plein milieu entre deux appels à .feed()."""
        f = _ThinkStreamFilter()
        chunks = ['Avant ', '<th', 'ink>caché', '</th', 'ink> après']
        out = ''.join(f.feed(c) for c in chunks)
        assert out == 'Avant  après'

    def test_content_before_and_after_block_both_visible(self):
        f = _ThinkStreamFilter()
        out = ''.join(f.feed(c) for c in ['Avant. ', '<think>', 'x', '</think>', ' Après.'])
        assert out == 'Avant.  Après.'

    def test_unclosed_block_never_emitted(self):
        """Si le flux s'arrête (timeout) avant la balise fermante, le bloc
        thinking en cours ne doit jamais apparaître dans la sortie visible."""
        f = _ThinkStreamFilter()
        out = ''.join(f.feed(c) for c in ['Début. ', '<think>', 'raisonnement qui ne finit jamais'])
        assert out == 'Début. '

    def test_multiple_blocks_in_stream(self):
        f = _ThinkStreamFilter()
        out = ''.join(f.feed(c) for c in [
            '<think>a</think>', 'Un. ', '<think>b</think>', 'Deux.',
        ])
        assert out == 'Un. Deux.'
