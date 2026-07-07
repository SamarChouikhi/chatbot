"""Tests unitaires — mcp_client/intents.py"""
import pytest
from mcp_client.intents import _detect_lang, is_static_intent


class TestDetectLang:
    def test_arabic_unicode(self):
        assert _detect_lang("مرحبا") == 'ar'

    def test_french_bonjour(self):
        assert _detect_lang("bonjour") == 'fr'

    def test_french_salut(self):
        assert _detect_lang("salut") == 'fr'

    def test_english_hello(self):
        assert _detect_lang("hello there") == 'en'

    def test_english_thanks(self):
        assert _detect_lang("thanks a lot") == 'en'

    def test_unknown_defaults_to_fr(self):
        assert _detect_lang("Konsumption von Wasser") == 'fr'

    def test_empty_defaults_to_fr(self):
        assert _detect_lang("") == 'fr'

    def test_abbrev_bjr_is_fr(self):
        assert _detect_lang("bjr") == 'fr'

    def test_abbrev_thx_is_en(self):
        assert _detect_lang("thx") == 'en'


class TestIsStaticIntentGreeting:
    def test_bonjour(self):
        intent, response = is_static_intent("bonjour")
        assert intent == 'greeting'
        assert "ARIA" in response

    def test_hello_english(self):
        intent, response = is_static_intent("hello")
        assert intent == 'greeting'

    def test_arabic_greeting(self):
        intent, response = is_static_intent("مرحبا")
        assert intent == 'greeting'

    def test_greeting_with_exclamation(self):
        intent, _ = is_static_intent("bonjour!")
        assert intent == 'greeting'

    def test_greeting_with_question_mark(self):
        intent, _ = is_static_intent("salut?")
        assert intent == 'greeting'

    def test_hi(self):
        intent, _ = is_static_intent("hi")
        assert intent == 'greeting'


class TestIsStaticIntentThanks:
    def test_merci(self):
        intent, _ = is_static_intent("merci")
        assert intent == 'thanks'

    def test_thank_you(self):
        intent, _ = is_static_intent("thank you")
        assert intent == 'thanks'

    def test_thx(self):
        intent, _ = is_static_intent("thx")
        assert intent == 'thanks'

    def test_arabic_shukran(self):
        intent, _ = is_static_intent("شكرا")
        assert intent == 'thanks'


class TestIsStaticIntentGoodbye:
    def test_au_revoir(self):
        intent, _ = is_static_intent("au revoir")
        assert intent == 'goodbye'

    def test_bye(self):
        intent, _ = is_static_intent("bye")
        assert intent == 'goodbye'

    def test_tchao(self):
        intent, _ = is_static_intent("tchao")
        assert intent == 'goodbye'


class TestIsStaticIntentHowRu:
    def test_ca_va(self):
        intent, _ = is_static_intent("ça va")
        assert intent == 'howru'

    def test_how_are_you(self):
        intent, _ = is_static_intent("how are you")
        assert intent == 'howru'


class TestIsStaticIntentWhoRu:
    def test_qui_es_tu(self):
        intent, _ = is_static_intent("qui es-tu")
        assert intent == 'whoru'

    def test_who_are_you(self):
        intent, _ = is_static_intent("who are you")
        assert intent == 'whoru'


class TestIsStaticIntentHelp:
    def test_aide(self):
        intent, _ = is_static_intent("aide")
        assert intent == 'help'

    def test_help(self):
        intent, _ = is_static_intent("help")
        assert intent == 'help'

    def test_help_response_contains_modules(self):
        _, response = is_static_intent("aide")
        assert "THL" in response or "eau" in response.lower()


class TestIsStaticIntentNegative:
    def test_data_question_not_static(self):
        intent, response = is_static_intent("quelle est la consommation en eau ce mois ?")
        assert intent is None
        assert response is None

    def test_long_greeting_not_static(self):
        intent, _ = is_static_intent("bonjour je voudrais savoir la température des capteurs")
        assert intent is None

    def test_empty_not_static(self):
        intent, _ = is_static_intent("")
        assert intent is None

    def test_anomaly_query_not_static(self):
        intent, _ = is_static_intent("y a-t-il des anomalies sur l'énergie aujourd'hui ?")
        assert intent is None

    def test_response_is_none_when_not_static(self):
        _, resp = is_static_intent("montre-moi les données eau")
        assert resp is None

    def test_no_match_when_too_long(self):
        # 81 caractères → dépasse _MAX_STATIC_LEN = 80
        long_q = "bonjour " + "x" * 73
        intent, _ = is_static_intent(long_q)
        assert intent is None
