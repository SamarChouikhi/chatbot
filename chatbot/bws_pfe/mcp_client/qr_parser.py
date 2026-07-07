import re

_QR_PATTERN = re.compile(r'\[QR:([^\]]+)\]\s*$', re.MULTILINE)


def parse_quick_replies(text: str) -> tuple[str, list[dict]]:
    """Extrait le tag [QR:...] de la fin du texte ARIA.

    Retourne (texte_sans_tag, liste_de_quick_replies).
    Si aucun tag trouvé, retourne (texte_original, []).
    """
    match = _QR_PATTERN.search(text)
    if not match:
        return text, []

    clean = text[:match.start()].rstrip()
    qr = []
    for part in match.group(1).split('|'):
        segs = part.split(':')
        if len(segs) >= 2:
            qr.append({'label': segs[0].strip(), 'value': ':'.join(segs[1:]).strip()})

    return clean, qr
