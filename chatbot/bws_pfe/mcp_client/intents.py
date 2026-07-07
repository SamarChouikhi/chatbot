import re
from typing import Optional, Tuple


def _detect_lang(text: str) -> str:
    """Détecte la langue du message parmi 'ar', 'fr', 'en'."""
    t = text.strip().lower()

    if re.search(r'[؀-ۿ]', text):
        return 'ar'

    fr_words = ['bonjour', 'bonsoir', 'salut', 'merci', 'au revoir', 'bonne',
                'comment', 'qui', 'coucou', 'bjr', 'bsr', 'slt', 'bnj', 'mrc',
                'tchao', 'aide', 'ca va', 'cc']
    if any(w in t for w in fr_words):
        return 'fr'

    en_words = ['hello', 'hi', 'hey', 'thanks', 'thank you', 'goodbye', 'bye',
                'how are you', 'who are you', 'what are you', 'help', 'good morning',
                'good evening', 'see you', 'thx']
    if any(w in t for w in en_words):
        return 'en'

    return 'fr'


STATIC_RESPONSES = {
    'greeting': {
        'fr': "Bonjour ! Je suis ARIA, votre assistant intelligent IOIT. Comment puis-je vous aider ?",
        'en': "Hello! I'm ARIA, your intelligent IOIT assistant. How can I help you?",
        'ar': "مرحباً! أنا ARIA، مساعدك الذكي. كيف يمكنني مساعدتك؟",
    },
    'thanks': {
        'fr': "De rien ! Je reste disponible pour toute question sur votre système.",
        'en': "You're welcome! Feel free to ask anything about your system.",
        'ar': "على الرحب والسعة! أنا هنا لأي سؤال حول نظامك.",
    },
    'goodbye': {
        'fr': "Au revoir ! N'hésitez pas à revenir si vous avez des questions.",
        'en': "Goodbye! Don't hesitate to come back if you have any questions.",
        'ar': "مع السلامة! لا تتردد في العودة إذا كان لديك أي أسئلة.",
    },
    'howru': {
        'fr': "Je fonctionne parfaitement ! Prêt à analyser vos données. Que puis-je faire pour vous ?",
        'en': "I'm running perfectly! Ready to analyze your data. What can I do for you?",
        'ar': "أنا بخير، شكراً! جاهز لتحليل بيانات نظامك. ماذا تريد؟",
    },
    'whoru': {
        'fr': "Je suis ARIA — Assistant de Renseignement Intelligent pour l'Automatisation. Je surveille et analyse votre infrastructure en temps réel.",
        'en': "I'm ARIA — Intelligent Reporting Assistant for Automation. I monitor and analyze your infrastructure in real time.",
        'ar': "أنا ARIA — مساعد ذكي لمراقبة وتحليل الأنظمة في الوقت الفعلي.",
    },
    'help': {
        'fr': (
            "Je peux vous aider avec :\n"
            "- **THL** — Température, humidité, luminosité en temps réel\n"
            "- **Eau (WM)** — Consommation, fuites, fraudes sur les compteurs d'eau\n"
            "- **Énergie (EN)** — Puissance, tension, courant, cosfi, THD\n"
            "- **Gaz (GM)** — Débit, consommation, fuites sur les compteurs de gaz\n"
            "- **Météo (SM)** — Vent, pression, température, UV\n"
            "- **Présence (PIR)** — Trafic et comptage de passages\n"
            "- **Flotte (Fuel)** — Consommation carburant, distance, vitesse\n"
            "- **Anomalies** — Détection sur tous les capteurs\n"
            "- **Rapports complets** et requêtes sur vos données\n\n"
            "Posez votre question !"
        ),
        'en': (
            "I can help with:\n"
            "- **THL** — Real-time temperature, humidity, light\n"
            "- **Water (WM)** — Consumption, leaks, fraud on water meters\n"
            "- **Energy (EN)** — Power, voltage, current, power factor, THD\n"
            "- **Gas (GM)** — Flow, consumption, leaks on gas meters\n"
            "- **Weather (SM)** — Wind, pressure, temperature, UV\n"
            "- **Presence (PIR)** — Traffic and footfall counting\n"
            "- **Fleet (Fuel)** — Fuel consumption, distance, speed\n"
            "- **Anomaly detection** — Across all sensor types\n"
            "- **Full reports** and custom data queries\n\n"
            "Just ask!"
        ),
        'ar': (
            "يمكنني المساعدة في:\n"
            "- **THL** — درجة الحرارة والرطوبة والإضاءة\n"
            "- **المياه (WM)** — الاستهلاك والتسربات والاحتيال\n"
            "- **الطاقة (EN)** — القدرة، الجهد، التيار، معامل القدرة\n"
            "- **الغاز (GM)** — التدفق والاستهلاك والتسربات\n"
            "- **الطقس (SM)** — الرياح والضغط ودرجة الحرارة\n"
            "- **الحضور (PIR)** — إحصاء الحركة والمرور\n"
            "- **الأسطول (Fuel)** — استهلاك الوقود والمسافة والسرعة\n"
            "- **كشف الشذوذات** على جميع المستشعرات\n"
            "- **التقارير الكاملة** والاستعلامات\n\n"
            "فقط اسأل!"
        ),
    },
}

# Patterns ancrés en début de message + ponctuation finale tolérée.
# Le groupe de fin \s*[!?.،؟]?\s*$ accepte la ponctuation mais rejette
# les phrases complètes qui dépassent la simple politesse.
STATIC_PATTERNS = {
    'greeting': r'^(bonjour|bonsoir|salut|coucou|bjr|bsr|slt|bnj|bnjr|bonne\s?journee|bonne\s?soiree|hello|hi|hey|good\s?morning|good\s?evening|good\s?afternoon|مرحبا|مرحب|السلام عليكم|السلام|صباح الخير|مساء الخير|صباح|مساء|اهلا|أهلاً)\s*[!?.،؟]?\s*$',
    'thanks'  : r'^(merci|mrc|mci|mrci|merci\s?beaucoup|merci\s?bien|thank\s?you|thanks|thx|ty|شكرا|شكراً|شكرا\s?جزيلا|عفواً)\s*[!?.،؟]?\s*$',
    'goodbye' : r'^(au revoir|a\s?bientot|tchao|bonne\s?nuit|bye|goodbye|see\s?you|مع السلامة|بالسلامة|وداعا|إلى اللقاء)\s*[!?.،؟]?\s*$',
    'howru'   : r'^(ca va|ça va|comment vas.tu|comment tu vas|comment allez.vous|how are you|how r u|كيف حالك|كيفك|كيف الحال|كيف\s?الأمور)\s*[!?.،؟]?\s*$',
    'whoru'   : r'^(qui es.tu|tu es qui|c quoi aria|c koi aria|tu es quoi|who are you|what are you|ما انت|من انت|ما هي aria|من أنت)\s*[!?.،؟]?\s*$',
    'help'    : r'^(aide|help|aidez.moi|besoin d.aide|que peux.tu faire|what can you do|ماذا تستطيع|كيف تساعدني|ماذا يمكنك فعله)\s*[!?.،؟]?\s*$',
}

# Limite portée à 80 caractères pour couvrir les salutations arabes longues
_MAX_STATIC_LEN = 80


def is_static_intent(question: str) -> Tuple[Optional[str], Optional[str]]:
    """Détecte les intents statiques (salutations, politesse) sans consommer de tokens LLM."""
    q = question.strip()
    if len(q) > _MAX_STATIC_LEN:
        return None, None
    q_lower = q.lower()
    for intent, pattern in STATIC_PATTERNS.items():
        if re.search(pattern, q_lower, re.IGNORECASE):
            lang     = _detect_lang(q)  # passer q (non lower) pour les caractères arabes
            response = STATIC_RESPONSES[intent].get(lang, STATIC_RESPONSES[intent]['fr'])
            return intent, response
    return None, None
