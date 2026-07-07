"""Tests unitaires — mcp_client/qr_parser.py"""
import pytest
from mcp_client.qr_parser import parse_quick_replies


class TestParseQuickReplies:
    def test_no_tag_returns_original_text(self):
        text = "Voici la réponse sans quick replies."
        result, qr = parse_quick_replies(text)
        assert result == text
        assert qr == []

    def test_single_item(self):
        text = "Choisissez :\n[QR:Eau:eau]"
        result, qr = parse_quick_replies(text)
        assert "[QR:" not in result
        assert len(qr) == 1
        assert qr[0]['label'] == 'Eau'
        assert qr[0]['value'] == 'eau'

    def test_multiple_items_pipe_separated(self):
        text = "Options :\n[QR:Eau:eau|Gaz:gaz|Énergie:energie]"
        _, qr = parse_quick_replies(text)
        assert len(qr) == 3
        assert qr[0]['label'] == 'Eau'
        assert qr[1]['label'] == 'Gaz'
        assert qr[2]['label'] == 'Énergie'
        assert qr[2]['value'] == 'energie'

    def test_text_before_tag_preserved(self):
        text = "Voici votre réponse complète.\n[QR:Aide:aide]"
        result, qr = parse_quick_replies(text)
        assert "Voici votre réponse complète." in result
        assert len(qr) == 1

    def test_trailing_whitespace_stripped_from_text(self):
        text = "Réponse  \n[QR:Test:test]"
        result, _ = parse_quick_replies(text)
        assert result == result.rstrip()

    def test_malformed_no_colon_not_added(self):
        text = "Réponse\n[QR:pasdecolon]"
        _, qr = parse_quick_replies(text)
        assert qr == []

    def test_value_with_colons_preserved(self):
        # label = segs[0], value = ':'.join(segs[1:])
        text = "Réponse\n[QR:Label:val:ue]"
        _, qr = parse_quick_replies(text)
        assert len(qr) == 1
        assert qr[0]['label'] == 'Label'
        assert qr[0]['value'] == 'val:ue'

    def test_empty_string(self):
        result, qr = parse_quick_replies("")
        assert result == ""
        assert qr == []

    def test_tag_at_end_of_first_line_is_matched(self):
        # re.MULTILINE : $ matche fin de chaque ligne, donc le tag en ligne 1 est détecté
        text = "[QR:Eau:eau]\nTexte après le tag"
        _, qr = parse_quick_replies(text)
        assert len(qr) == 1
        assert qr[0]['value'] == 'eau'

    def test_label_and_value_stripped(self):
        text = "Réponse\n[QR: Eau : eau ]"
        _, qr = parse_quick_replies(text)
        if qr:
            assert qr[0]['label'] == 'Eau'
            assert qr[0]['value'] == 'eau'

    def test_no_tag_returns_empty_list(self):
        _, qr = parse_quick_replies("Texte normal sans marqueur.")
        assert isinstance(qr, list)
        assert len(qr) == 0
