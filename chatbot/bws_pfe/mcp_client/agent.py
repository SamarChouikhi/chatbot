import asyncio
import logging
import os
import re
import time
from collections import OrderedDict
from typing import Any, Dict

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools  import load_mcp_tools
from langgraph.checkpoint.memory import MemorySaver
# create_react_agent importé en différé dans initialize() pour éviter
# langgraph.prebuilt → langchain_core.language_models → transformers → torch au chargement du module
from langchain_core.messages import ToolMessage

from mcp_client.config       import MCP_SERVER_URL
from mcp_client.history      import MySQLHistoryManager
from mcp_client.intents      import is_static_intent
from mcp_client.llm_factory  import LLMFactory
from mcp_client.prompt       import build_full_prompt
from mcp_client.qr_parser    import parse_quick_replies
from mcp_client.preprocessor import analyze as analyze_intent
from mcp_client.output_guard import check_output, needs_retry, build_retry_hint

logger = logging.getLogger('aria.agent')

# Labels affichés dans le chatbot pendant l'utilisation d'un outil MCP (fr/en/ar)
_TOOL_LABELS: dict[str, dict[str, str]] = {
    'wm_analysis'             : {'fr': '💧 Analyse de la consommation eau…',            'en': '💧 Analyzing water consumption…',              'ar': '💧 تحليل استهلاك المياه…'},
    'energy_analysis'         : {'fr': '⚡ Analyse de la consommation électrique…',      'en': '⚡ Analyzing electricity consumption…',         'ar': '⚡ تحليل استهلاك الكهرباء…'},
    'gm_analysis'             : {'fr': '🔥 Analyse de la consommation gaz…',            'en': '🔥 Analyzing gas consumption…',                'ar': '🔥 تحليل استهلاك الغاز…'},
    'fuel_analysis'           : {'fr': '⛽ Analyse de la consommation carburant…',       'en': '⛽ Analyzing fuel consumption…',                'ar': '⛽ تحليل استهلاك الوقود…'},
    'wm_trend'                : {'fr': '💧 Génération de la courbe eau…',               'en': '💧 Building water trend chart…',                'ar': '💧 إنشاء منحنى المياه…'},
    'energy_trend'            : {'fr': '⚡ Génération de la courbe électrique…',        'en': '⚡ Building electricity trend chart…',           'ar': '⚡ إنشاء منحنى الكهرباء…'},
    'gm_trend'                : {'fr': '🔥 Génération de la courbe gaz…',               'en': '🔥 Building gas trend chart…',                  'ar': '🔥 إنشاء منحنى الغاز…'},
    'fuel_trend'              : {'fr': '⛽ Génération de la courbe carburant…',          'en': '⛽ Building fuel trend chart…',                  'ar': '⛽ إنشاء منحنى الوقود…'},
    'thl_analysis'            : {'fr': '🌡️ Lecture des capteurs THL…',                  'en': '🌡️ Reading THL sensors…',                      'ar': '🌡️ قراءة مستشعرات THL…'},
    'alerts_summary'          : {'fr': '🚨 Vérification des alertes actives…',          'en': '🚨 Checking active alerts…',                    'ar': '🚨 التحقق من التنبيهات النشطة…'},
    'realtime_data'           : {'fr': '📡 Récupération données temps réel…',           'en': '📡 Fetching real-time data…',                   'ar': '📡 جلب البيانات في الوقت الفعلي…'},
    'anomaly_detection'       : {'fr': '🔍 Détection des anomalies…',                   'en': '🔍 Detecting anomalies…',                       'ar': '🔍 اكتشاف الشذوذ…'},
    'ad_analysis'             : {'fr': '🧠 Analyse IA des anomalies ML…',               'en': '🧠 AI analysis of ML anomalies…',               'ar': '🧠 تحليل الذكاء الاصطناعي للشذوذ…'},
    'get_upcoming_predictions': {'fr': '📈 Récupération des prédictions…',              'en': '📈 Fetching predictions…',                      'ar': '📈 جلب التوقعات…'},
    'get_recommendations'     : {'fr': '💡 Chargement des recommandations personnalisées…', 'en': '💡 Loading personalized recommendations…', 'ar': '💡 تحميل التوصيات الشخصية…'},
    'database_summary'        : {'fr': '🗄️ Analyse de la base de données…',             'en': '🗄️ Analyzing the database…',                   'ar': '🗄️ تحليل قاعدة البيانات…'},
    'execute_query'           : {'fr': '🔎 Exécution de la requête…',                   'en': '🔎 Running the query…',                        'ar': '🔎 تنفيذ الاستعلام…'},
    'search_in_table'         : {'fr': '🔎 Recherche dans les données…',                'en': '🔎 Searching data…',                            'ar': '🔎 البحث في البيانات…'},
    'count_rows'              : {'fr': '🔢 Comptage des enregistrements…',              'en': '🔢 Counting records…',                          'ar': '🔢 عد السجلات…'},
    'list_tables'             : {'fr': '📋 Listage des tables…',                        'en': '📋 Listing tables…',                            'ar': '📋 سرد الجداول…'},
    'describe_table'          : {'fr': '📐 Description de la table…',                   'en': '📐 Describing the table…',                      'ar': '📐 وصف الجدول…'},
}
_DEFAULT_TOOL_LABEL = {'fr': '🔍 Recherche de données…', 'en': '🔍 Fetching data…', 'ar': '🔍 جلب البيانات…'}

# Messages d'état/erreur du flux SSE (fr/en/ar)
_UI_STRINGS: dict[str, dict[str, str]] = {
    'thinking'            : {'fr': 'ARIA analyse votre question…',
                              'en': 'ARIA is analyzing your question…',
                              'ar': 'ARIA يحلل سؤالك…'},
    'no_answer'           : {'fr': 'Désolé, je n\'ai pas pu générer de réponse. Reformulez votre question.',
                              'en': 'Sorry, I could not generate a response. Please rephrase your question.',
                              'ar': 'عذرًا، لم أتمكن من إنشاء رد. يرجى إعادة صياغة سؤالك.'},
    'system_error'        : {'fr': 'Erreur système. Réessayez.',
                              'en': 'System error. Please try again.',
                              'ar': 'خطأ في النظام. حاول مرة أخرى.'},
    'service_unavailable' : {'fr': 'Service temporairement indisponible. Réessayez.',
                              'en': 'Service temporarily unavailable. Please try again.',
                              'ar': 'الخدمة غير متوفرة مؤقتًا. حاول مرة أخرى.'},
    'no_response'         : {'fr': 'Réponse indisponible.',
                              'en': 'Response unavailable.',
                              'ar': 'الرد غير متوفر.'},
    'analysis_too_long'   : {'fr': 'Analyse trop longue. Essayez une période plus courte (ex: 24h).',
                              'en': 'Analysis took too long. Try a shorter period (e.g. 24h).',
                              'ar': 'استغرق التحليل وقتًا طويلاً. جرب فترة أقصر (مثلاً 24 ساعة).'},
}


def _tool_label(tool_name: str, lang: str) -> str:
    entry = _TOOL_LABELS.get(tool_name)
    if entry:
        return entry.get(lang, entry['fr'])
    return _DEFAULT_TOOL_LABEL.get(lang, _DEFAULT_TOOL_LABEL['fr'])


def _ui(key: str, lang: str) -> str:
    return _UI_STRINGS[key].get(lang, _UI_STRINGS[key]['fr'])

# Outil MCP → module requis (None = outil général, toujours disponible)
_TOOL_MODULE_MAP: dict[str, str | None] = {
    'wm_analysis'      : 'eau',
    'energy_analysis'  : 'énergie électrique',
    'gm_analysis'      : 'gaz',
    'fuel_analysis'    : 'carburant',
    'wm_trend'         : 'eau',
    'energy_trend'     : 'énergie électrique',
    'gm_trend'         : 'gaz',
    'fuel_trend'       : 'carburant',
    'thl_analysis'     : 'équipements/capteurs',
    'alerts_summary'   : 'alertes',
    'realtime_data'    : None,
    'anomaly_detection'      : None,
    'get_upcoming_predictions': None,
    'database_summary' : None,
    'list_tables'      : None,
    'describe_table'   : None,
    'count_rows'       : None,
    'execute_query'    : None,
    'search_in_table'  : None,
    'ad_analysis'        : None,
    'get_recommendations': None,
}

# Module → types de données realtime_data autorisés pour ce module
_MODULE_TO_REALTIME: dict[str, list[str]] = {
    'équipements/capteurs': ['thl', 'sm', 'pir', 'ls'],
    'eau'                 : ['wm'],
    'énergie électrique'  : ['en'],
    'gaz'                 : ['gm'],
    'carburant'           : [],
    'alertes'             : [],
    'dashboard'           : [],
    'rapports'            : [],
}

_LANG_NAMES: dict[str, str] = {
    'fr': 'French (français)',
    'ar': 'Arabic (العربية)',
    'en': 'English',
}

TIMEOUT_BY_BACKEND: dict[str, float] = {
    'ollama'     : 180.0,
    'groq'       : 120.0,  # relevé 75→120 : la génération est rapide mais les appels outils DB peuvent prendre 30-60s
    'gemini'     : 120.0,
    'openrouter' : 300.0,
    'huggingface': 120.0,
    'cerebras'   : 120.0,
}
DEFAULT_TIMEOUT = 120.0

MAX_CHARS_BY_BACKEND: dict[str, int] = {
    'groq'       : 600,    # relevé de 400→600 : 400 coupait trop l'historique utile
    'huggingface': 800,
    'ollama'     : 1200,
    'gemini'     : 1000,
    'openrouter' : 1000,
    'cerebras'   : 800,
}
DEFAULT_MAX_CHARS = 800

# Opt 2 — Nombre de messages chargés depuis MySQL selon le backend.
_HISTORY_LIMIT_BY_BACKEND: dict[str, int] = {
    'groq'       : 4,  # réduit pour éviter 413 sur llama-3.1-8b-instant (TPM limit 6000)
    'huggingface': 8,
    'openrouter' : 12,
    'gemini'     : 12,
    'cerebras'   : 10,
    'ollama'     : 15,
}
_DEFAULT_HISTORY_LIMIT = 10

# Opt 3 — Limite le nombre d'étapes ReAct (1 outil = 2 étapes : AI + Tool).
# 16 étapes = 7 appels d'outils max — nécessaire pour le FULL REPORT (9 outils).
_REACT_RECURSION_LIMIT = 16

# Charts affichés uniquement si l'utilisateur les demande explicitement
# (comparaison, graphique, courbe, visualisation...) — pas systématiquement à chaque réponse.
_CHART_RE = re.compile(
    r'\bgraphiques?\b|\bgraphs?\b|\bcharts?\b|\bcourbes?\b|\bdiagrammes?\b'
    r'|\bplot(s|te[rz]?)?\b|\bvisualis[eé]|compar[eaéiè]',
    re.IGNORECASE,
)


class _ThinkStreamFilter:
    """Supprime les blocs <think>…</think> du stream token par token.
    Nécessaire pour Qwen3/reasoning models dont le raisonnement interne
    serait autrement visible dans le chat (Angular strip les balises HTML
    mais affiche leur contenu)."""

    _OPEN  = '<think>'
    _CLOSE = '</think>'

    def __init__(self):
        self._buf      = ''
        self._thinking = False

    def feed(self, token: str) -> str:
        """Retourne la partie visible du token (hors blocs thinking). Peut retourner ''."""
        self._buf += token
        out = ''
        while self._buf:
            if self._thinking:
                end = self._buf.find(self._CLOSE)
                if end == -1:
                    self._buf = ''   # bloc non fermé — vider et attendre la suite
                    break
                self._buf    = self._buf[end + len(self._CLOSE):]
                self._thinking = False
            else:
                start = self._buf.find(self._OPEN)
                if start == -1:
                    out       += self._buf
                    self._buf  = ''
                    break
                out           += self._buf[:start]
                self._buf      = self._buf[start + len(self._OPEN):]
                self._thinking = True
        return out

# Mapping capteur → outil d'analyse pour le routing hint.
_SENSOR_ANALYSIS_TOOL: dict[str, str] = {
    'thl' : 'thl_analysis',
    'wm'  : 'wm_analysis',
    'en'  : 'energy_analysis',
    'gm'  : 'gm_analysis',
    'fuel': 'fuel_analysis',
}

# Mapping capteur → domaine pour get_upcoming_predictions / get_recommendations.
_SENSOR_TO_DOMAIN: dict[str, str] = {
    'en'  : 'energy',
    'wm'  : 'water',
    'gm'  : 'gas',
    'fuel': 'fuel',
}


# Mots indiquant une confirmation de l'utilisateur (réponse courte à une proposition ARIA)
_CONFIRMATION_WORDS = frozenset({
    'oui', 'ok', 'yes', 'ouais', 'vas-y', 'go', 'lance', 'confirme',
    "d'accord", 'd accord', 'allez', 'absolument', 'exactement',
    'tout à fait', 'tout a fait', 'bien sûr', 'bien sur', 'parfait',
    'allons-y', 'continuons', 'proceed', 'نعم', 'بالتأكيد',
})


def _is_confirmation(q: str) -> bool:
    """Détecte si la question est une simple confirmation (oui / ok / go…)."""
    normalized = q.lower().strip().rstrip('!.,? ')
    return normalized in _CONFIRMATION_WORDS


def _build_confirmation_hint(question: str, history: list[dict]) -> str:
    """Pour une confirmation, extrait l'action proposée dans le dernier message ARIA
    et génère un routing hint précis pour éviter une étape de raisonnement LLM."""
    if not _is_confirmation(question) or not history:
        return ''
    for msg in reversed(history[-6:]):
        if msg['role'] != 'assistant':
            continue
        content = msg['content']
        c_lower = content.lower()

        # Proposait une analyse anomalie
        if 'anomal' in c_lower and any(k in c_lower for k in ['analys', 'détect', 'detect', 'lance']):
            period = '48h' if '48h' in c_lower or '48 heure' in c_lower else '24h'
            return (
                f'[CONFIRMATION→ utilisateur confirme. '
                f'Lance anomaly_detection("{period}") + alerts_summary immédiatement. '
                f'Ne re-demande PAS confirmation.]'
            )

        # Proposait une analyse eau / compteur
        if any(k in c_lower for k in ['eau', 'compteur eau', 'consommation eau', 'wm', 'fuite']):
            period = '48h' if ('48h' in c_lower or '48 heure' in c_lower) else '24h'
            return (
                f'[CONFIRMATION→ utilisateur confirme. '
                f'Lance realtime_data("wm") → wm_analysis("{period}") immédiatement. '
                f'Ne re-demande PAS confirmation.]'
            )

        # Proposait une analyse électrique
        if any(k in c_lower for k in ['électr', 'énergi', 'kwh', 'watt', 'tension']):
            period = '48h' if ('48h' in c_lower or '48 heure' in c_lower) else '24h'
            return (
                f'[CONFIRMATION→ utilisateur confirme. '
                f'Lance realtime_data("en") → energy_analysis("{period}") immédiatement. '
                f'Ne re-demande PAS confirmation.]'
            )

        # Proposait une analyse gaz
        if any(k in c_lower for k in ['gaz', 'gm', 'fuite gaz']):
            period = '48h' if ('48h' in c_lower or '48 heure' in c_lower) else '24h'
            return (
                f'[CONFIRMATION→ utilisateur confirme. '
                f'Lance realtime_data("gm") → gm_analysis("{period}") immédiatement. '
                f'Ne re-demande PAS confirmation.]'
            )

        # Proposition générique d'analyse
        if any(k in c_lower for k in ['analys', 'lance', 'puis-je', 'voulez-vous', 'souhaitez', 'shall i', 'want me to']):
            return (
                '[CONFIRMATION→ utilisateur confirme. '
                'Exécute immédiatement l\'analyse proposée précédemment. '
                'Ne re-demande PAS confirmation.]'
            )

    return ''


_PRED_CONTEXT_SIGNALS = frozenset({
    'prévu', 'prévue', 'prévus', 'prédiction', 'prévision', 'prévisions',
    'risque', 'risques', 'forecast', 'aucune anomalie prévue',
    'prochaines heures', 'à venir', 'get_upcoming', 'horizon',
})


def _has_prediction_context(history: list[dict] | None) -> bool:
    """Retourne True si la dernière réponse ARIA portait sur des prédictions/risques futurs."""
    if not history:
        return False
    for msg in reversed(history[-4:]):
        if msg.get('role') == 'assistant':
            content = msg.get('content', '').lower()
            if any(s in content for s in _PRED_CONTEXT_SIGNALS):
                return True
    return False


def _build_routing_hint(intent, history: list[dict] | None = None) -> str:
    """Construit un hint système compact qui guide le LLM vers le bon outil
    sans lui laisser raisonner dessus — économise 1 étape de réflexion LLM."""
    # Confirmation d'une proposition ARIA → hint contextuel prioritaire
    if history and _is_confirmation(intent.raw_question):
        conf_hint = _build_confirmation_hint(intent.raw_question, history)
        if conf_hint:
            return conf_hint

    qt     = intent.query_type
    sensor = intent.sensor_type
    period = intent.period or '24h'

    # Prediction et recommendation ne requièrent pas de sensor_type détecté
    if qt == 'prediction':
        domain  = _SENSOR_TO_DOMAIN.get(sensor, 'all') if sensor else 'all'
        q_lower = intent.raw_question.lower()
        horizon = 48 if '48' in q_lower else 24
        return (f'[ROUTING→ get_upcoming_predictions(domain="{domain}", horizon_hours={horizon})'
                f' → anomaly_detection("24h")]')
    if qt == 'recommendation':
        domain = _SENSOR_TO_DOMAIN.get(sensor, 'all') if sensor else 'all'
        return f'[ROUTING→ get_recommendations(domain="{domain}", limit=5)]'

    if not intent.is_data_query or not sensor:
        return ''

    if qt == 'report' or sensor == 'all':
        if _has_prediction_context(history):
            return ('[ROUTING→ get_upcoming_predictions(domain="all", horizon_hours=48)'
                    ' → ad_analysis(domain="energy") → anomaly_detection("24h")'
                    ' → realtime_data("all") → alerts_summary("all")]')
        return '[ROUTING→ FULL REPORT chain]'
    if qt == 'anomaly':
        return f'[ROUTING→ anomaly_detection("{period}") + alerts_summary]'
    if qt == 'realtime' or sensor in ('pir', 'ls', 'sm'):
        return f'[ROUTING→ realtime_data("{sensor}")]'
    tool = _SENSOR_ANALYSIS_TOOL.get(sensor)
    if tool:
        return f'[ROUTING→ realtime_data("{sensor}") → {tool}("{period}")]'
    return ''


def detect_response_level(result: dict) -> str:
    """Détermine si la réponse est basée sur des données réelles (outils) ou sur des connaissances générales."""
    for msg in result.get('messages', []):
        if isinstance(msg, ToolMessage):
            return 'data'
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            return 'data'
    return 'knowledge'


def _get_timeout(backend: str) -> float:
    return float(
        os.getenv(f'{backend.upper()}_TIMEOUT', TIMEOUT_BY_BACKEND.get(backend, DEFAULT_TIMEOUT))
    )


async def _stream_with_timeout(gen, timeout_sec: float):
    """Itère sur astream_events() avec un timeout global.
    Si aucun événement n'arrive avant l'échéance, lève asyncio.TimeoutError."""
    deadline = time.time() + timeout_sec
    try:
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise asyncio.TimeoutError()
            try:
                event = await asyncio.wait_for(gen.__anext__(), timeout=remaining)
            except StopAsyncIteration:
                return
            yield event
    finally:
        try:
            await gen.aclose()
        except Exception:
            pass


def _extract_tool_output(output_data) -> str:
    """Extrait la string JSON depuis un on_tool_end output (ToolMessage ou string brute)."""
    if output_data is None:
        return ''
    if hasattr(output_data, 'content'):
        content = output_data.content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(item.get('text', str(item)))
                else:
                    parts.append(str(item))
            return ' '.join(parts)
        return str(content)
    return str(output_data)


async def _save_static_bg(
    history, thread_id: str, question: str, user_id: str, static_resp: str, start: float
):
    """Persiste en arrière-plan les deux messages d'un échange statique."""
    try:
        await asyncio.to_thread(
            history.save_message, thread_id, 'user', question,
            content_normalized=question.strip().lower(), user_id=user_id,
        )
        await asyncio.to_thread(
            history.save_message, thread_id, 'assistant', static_resp,
            level='static', backend='static', duration=time.time() - start,
        )
    except Exception as e:
        logger.warning(f'[STATIC SAVE] {e}')


class AriaAgent:

    # Purge le checkpointer principal toutes les N requêtes pour éviter
    # l'accumulation de thread_ids uniques dans MemorySaver
    _CHECKPOINTER_PURGE_EVERY = 500

    def __init__(self):
        self.executor        = None
        self.model_name      = None
        self.backend         = None
        self._history        = None
        self.llm             = None
        self.tools           = None
        self._initialized    = False
        self._lock           = None  # protège le remplacement du LLM lors d'un fallback
        self._cache_lock     = None  # protège la construction des executors par module
        self._cached_prompt  = None
        self._checkpointer   = MemorySaver()
        self._request_count  = 0     # compteur pour la purge périodique du checkpointer
        self._executor_cache: OrderedDict[frozenset, Any] = OrderedDict()
        self._executor_cache_max = 20  # max combinaisons de modules en cache
        self._mcp_client      = None
        self._mcp_session_ctx = None  # session SSE persistante — évite reconnexion par outil
        self._cra             = None  # create_react_agent, chargé dans initialize()

    async def initialize(self):
        if self._initialized:
            return

        self._lock       = asyncio.Lock()
        self._cache_lock = asyncio.Lock()
        logger.info('Initialisation ARIA Agent...')

        # Import différé : déclenche langgraph.prebuilt → langchain_core → transformers → torch
        # Fait ici et non au chargement du module pour ne pas bloquer uvicorn au démarrage.
        if self._cra is None:
            from langgraph.prebuilt import create_react_agent
            self._cra = create_react_agent

        # Init DB en premier — indépendant du MCP, disponible même si MCP est en retard
        if self._history is None:
            self._history = MySQLHistoryManager()

        # client.session() maintient la connexion SSE ouverte pour toute la durée de vie
        # de l'agent, évitant une reconnexion à chaque appel d'outil.
        self._mcp_client      = MultiServerMCPClient({'aria': {'url': MCP_SERVER_URL, 'transport': 'sse'}})
        self._mcp_session_ctx = self._mcp_client.session('aria')
        mcp_session           = await self._mcp_session_ctx.__aenter__()
        self.tools            = await load_mcp_tools(mcp_session)
        logger.info(f'MCP: {len(self.tools)} outils → {[t.name for t in self.tools]}')

        factory = LLMFactory()
        self.llm, self.model_name, self.backend = factory.create()
        logger.info(f'LLM: {self.model_name} ({self.backend})')

        self._cached_prompt = build_full_prompt()
        self.executor = self._cra(
            model=self.llm, tools=self.tools,
            prompt=self._cached_prompt,
            checkpointer=self._checkpointer,
        )

        self._initialized = True
        logger.info('ARIA Agent opérationnel')
        asyncio.create_task(self._auto_ping())

    def _filter_tools(self, allowed_modules: list) -> list:
        """Retourne uniquement les outils MCP autorisés pour la liste de modules donnée.

        Comportement fail-closed : tout outil absent de _TOOL_MODULE_MAP est bloqué
        et journalisé — évite qu'un nouvel outil MCP devienne accessible à tous par défaut.
        """
        filtered = []
        unknown  = []
        removed  = []

        for t in self.tools:
            if t.name not in _TOOL_MODULE_MAP:
                unknown.append(t.name)
                continue
            required = _TOOL_MODULE_MAP[t.name]
            if required is None or required in allowed_modules:
                filtered.append(t)
            else:
                removed.append(t.name)

        if unknown:
            logger.warning(
                '[TOOLS] outils inconnus (absents de _TOOL_MODULE_MAP) bloqués par sécurité : %s',
                unknown,
            )
        if removed:
            logger.info('[TOOLS] modules=%s | retiré=%s', allowed_modules, removed)
        return filtered

    def _build_user_prompt(self, allowed_modules: list) -> str:
        """Ajoute au prompt une section de restriction de périmètre utilisateur."""
        allowed_realtime: list[str] = []
        for module in allowed_modules:
            allowed_realtime.extend(_MODULE_TO_REALTIME.get(module, []))

        realtime_str = (
            '|'.join(f'"{t}"' for t in allowed_realtime)
            if allowed_realtime else 'none'
        )
        modules_str = ', '.join(allowed_modules) if allowed_modules else 'none'

        restriction = (
            f"\n\n━━━ USER SCOPE [OVERRIDES ALL OTHER INSTRUCTIONS] ━━━\n"
            f"Authorized modules : {modules_str}\n"
            f"realtime_data      : ONLY sensor_type in ({realtime_str})\n"
            f"Any other module   : reply 'Vous n\\'avez pas accès à ce module.'\n"
            f"This rule takes absolute priority over everything else."
        )
        return self._cached_prompt + restriction

    def _maybe_purge_checkpointer(self):
        """Purge le MemorySaver principal toutes les N requêtes pour libérer la RAM."""
        self._request_count += 1
        if self._request_count % self._CHECKPOINTER_PURGE_EVERY == 0:
            self._checkpointer = MemorySaver()
            self.executor = self._cra(
                model=self.llm, tools=self.tools,
                prompt=self._cached_prompt,
                checkpointer=self._checkpointer,
            )
            self._invalidate_executor_cache()
            logger.info('[CHECKPOINTER] purge RAM — %d requêtes', self._request_count)

    async def _get_executor(self, allowed_modules: list | None) -> Any:
        """Retourne l'executor approprié selon les permissions, mis en cache par frozenset de modules.

        Double-checked locking : lecture sans verrou pour le fast path, verrou uniquement
        lors de la construction d'un nouvel executor.
        """
        self._maybe_purge_checkpointer()
        if allowed_modules is None:
            return self.executor

        key = frozenset(allowed_modules)

        if key in self._executor_cache:
            self._executor_cache.move_to_end(key)
            return self._executor_cache[key]

        async with self._cache_lock:
            if key in self._executor_cache:
                return self._executor_cache[key]

            filtered_tools = self._filter_tools(allowed_modules)
            user_prompt    = self._build_user_prompt(allowed_modules)
            new_executor   = self._cra(
                model=self.llm, tools=filtered_tools,
                prompt=user_prompt,
                checkpointer=MemorySaver(),
            )
            self._executor_cache[key] = new_executor
            self._executor_cache.move_to_end(key)
            # LRU éviction : supprime l'entrée la plus ancienne si dépassement
            if len(self._executor_cache) > self._executor_cache_max:
                evicted = next(iter(self._executor_cache))
                del self._executor_cache[evicted]
                logger.debug('[EXECUTOR CACHE] éviction LRU — %s', evicted)
            logger.info(
                f'[EXECUTOR CACHE] +1 | modules={sorted(allowed_modules)} | '
                f'tools={len(filtered_tools)}/{len(self.tools)} | '
                f'cache_size={len(self._executor_cache)}'
            )
            return new_executor

    def _invalidate_executor_cache(self):
        count = len(self._executor_cache)
        self._executor_cache.clear()
        if count:
            logger.info(f'[EXECUTOR CACHE] invalidé ({count} entrée(s))')

    async def close(self):
        """Ferme proprement la session SSE vers le serveur MCP."""
        if self._mcp_session_ctx is not None:
            try:
                await self._mcp_session_ctx.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f'[MCP CLOSE] {e}')
            finally:
                self._mcp_session_ctx = None
                self._mcp_client      = None

    def get_history_manager(self) -> MySQLHistoryManager:
        return self._history

    def is_ready(self) -> bool:
        return self._initialized

    def handle_static(self, question: str, thread_id: str, user_id: str, start: float) -> str | None:
        """Vérifie si la question est un intent statique (salutation, merci…).
        Si oui : planifie la sauvegarde en arrière-plan et retourne la réponse prête.
        Si non : retourne None — le pipeline LLM doit prendre le relai.
        0 token LLM consommé dans tous les cas."""
        intent, response = is_static_intent(question)
        if not intent:
            return None
        asyncio.create_task(
            _save_static_bg(self._history, thread_id, question, user_id, response, start)
        )
        return response

    def _build_messages_input(
        self, history: list, question: str, lang: str = 'fr', routing_hint: str = ''
    ) -> list:
        """Tronque l'historique aux limites de la fenêtre contextuelle du backend actif."""
        max_chars = MAX_CHARS_BY_BACKEND.get(self.backend, DEFAULT_MAX_CHARS)
        if self.backend == 'groq' and self.model_name and '8b' in self.model_name:
            max_chars = 150  # llama-3.1-8b-instant : limite TPM 6000 tokens

        lang_name = _LANG_NAMES.get(lang, 'French (français)')
        messages  = [('system', f'PLATFORM_LANG={lang_name}. Respond ONLY in {lang_name}. Do not switch language regardless of the question language.')]
        for m in history:
            role    = 'human' if m['role'] == 'user' else 'ai'
            content = m['content']
            if len(content) > max_chars:
                content = content[:max_chars] + '...'
            messages.append((role, content))
        if routing_hint:
            messages.append(('system', routing_hint))
        messages.append(('human', question))
        return messages

    async def process(
        self, question: str, thread_id: str,
        user_id: str = 'default_user',
        allowed_modules: list | None = None,
        lang: str = 'fr',
    ) -> Dict:
        if not self._initialized:
            await self.initialize()

        start = time.time()

        await asyncio.to_thread(
            self._history.save_message, thread_id, 'user', question,
            content_normalized=question.strip().lower(), user_id=user_id,
        )

        hist_limit = _HISTORY_LIMIT_BY_BACKEND.get(self.backend, _DEFAULT_HISTORY_LIMIT)
        history = await asyncio.to_thread(
            self._history.get_conversation_history, thread_id, limit=hist_limit
        )
        if len(history) > 1 and history[-1]['role'] == 'user':
            history = history[:-1]
        elif len(history) == 1 and history[-1]['role'] == 'user':
            history = []

        intent         = analyze_intent(question, history)
        hint           = _build_routing_hint(intent, history)
        messages_input = self._build_messages_input(history, question, lang, routing_hint=hint)
        executor       = await self._get_executor(allowed_modules)
        exec_thread_id = f'{thread_id}_{int(time.time() * 1000)}'
        config         = {'recursion_limit': _REACT_RECURSION_LIMIT,
                          'configurable': {'thread_id': exec_thread_id}}
        timeout        = _get_timeout(self.backend)

        try:
            result      = await asyncio.wait_for(
                executor.ainvoke({'messages': messages_input}, config=config),
                timeout=timeout,
            )
            answer      = result['messages'][-1].content
            level       = detect_response_level(result)
            tools_used  = [m.name for m in result.get('messages', [])
                           if isinstance(m, ToolMessage)]

            # ── Quality gate + retry unique ───────────────────────────────
            report = check_output(answer, tools_used, intent)
            if needs_retry(report):
                logger.info(
                    f'[QUALITY GATE] score={report.score:.2f} — retry '
                    f'(is_clean={report.is_clean}, tools={report.tools_called_ok})'
                )
                retry_q      = build_retry_hint(question, report)
                retry_input  = self._build_messages_input(history, retry_q, lang)
                retry_config = {'recursion_limit': _REACT_RECURSION_LIMIT,
                                'configurable': {'thread_id': f'{thread_id}_retry'}}
                try:
                    retry_result = await asyncio.wait_for(
                        executor.ainvoke({'messages': retry_input}, config=retry_config),
                        timeout=timeout,
                    )
                    retry_answer = retry_result['messages'][-1].content
                    retry_tools  = [m.name for m in retry_result.get('messages', [])
                                    if isinstance(m, ToolMessage)]
                    retry_report = check_output(retry_answer, retry_tools, intent)
                    if retry_report.score > report.score:
                        answer, level = retry_answer, detect_response_level(retry_result)
                        logger.info(f'[QUALITY GATE] retry amélioré: {report.score:.2f}→{retry_report.score:.2f}')
                    else:
                        logger.info(f'[QUALITY GATE] retry sans gain, réponse originale conservée')
                except Exception as retry_err:
                    logger.warning(f'[QUALITY GATE] retry échoué: {str(retry_err)[:60]}')

            duration = time.time() - start
            msg_id   = await asyncio.to_thread(
                self._history.save_message, thread_id, 'assistant', answer,
                level=level, backend=f'{self.backend}/{self.model_name}', duration=duration,
            )
            logger.info(f'[{level.upper()}/{duration:.1f}s] [{self.model_name}] {question[:60]}')

            if not history:
                asyncio.create_task(self._auto_title(thread_id, question))

            return {'answer': answer, 'level': level, 'duration': duration,
                    'backend': self.backend, 'model': self.model_name, 'message_id': msg_id,
                    'quality_score': round(report.score, 2)}

        except Exception as e:
            err      = str(e)
            is_quota = isinstance(e, asyncio.TimeoutError) or any(k in err.lower() for k in [
                '413', 'too large', 'rate_limit', 'rate limit', '429',
                'failed to call a function', 'failed_generation',
                'timeout', 'timed out', 'readtimeout', 'apitimeouterror',
                'connection error', 'apiconnectionerror', 'connectionerror',
                'cannot connect', 'connection refused', 'network', 'unreachable',
            ])

            if is_quota:
                is_timeout = isinstance(e, asyncio.TimeoutError) or any(
                    k in err.lower() for k in ['timeout', 'timed out', 'readtimeout', 'apitimeouterror']
                )
                is_connection_error = any(k in err.lower() for k in [
                    'connection error', 'apiconnectionerror', 'connectionerror',
                    'cannot connect', 'connection refused', 'unreachable',
                ])
                log_reason = (
                    'TIMEOUT'          if is_timeout         else
                    'CONNECTION_ERROR' if is_connection_error else
                    'QUOTA/RATE/FUNC'
                )
                logger.warning(f'[{log_reason}] Tentative de fallback LLM ({self.backend}/{self.model_name})')

                async with self._lock:
                    try:
                        factory = LLMFactory()
                        if self.backend == 'groq':
                            if not is_timeout and not is_connection_error:
                                current_key = factory.key_manager.get_groq_key(self.model_name)
                                if current_key:
                                    factory.key_manager.mark_groq_exhausted(self.model_name, current_key)
                        elif self.backend == 'openrouter':
                            if not is_timeout and not is_connection_error:
                                current_key = factory.key_manager.get_openrouter_key()
                                if current_key:
                                    factory.key_manager.mark_openrouter_exhausted(current_key)
                        self.llm, self.model_name, self.backend = factory.create()
                        self.executor = self._cra(
                            model=self.llm, tools=self.tools,
                            prompt=self._cached_prompt,
                            checkpointer=self._checkpointer,
                        )
                        self._invalidate_executor_cache()
                        logger.info(f'[FALLBACK] Nouveau backend: {self.backend}/{self.model_name}')
                    except Exception as swap_err:
                        logger.error(f'[FALLBACK SWAP ERROR] {swap_err}')
                        return {'answer': _ui('service_unavailable', lang),
                                'level': 'error', 'duration': time.time() - start,
                                'backend': self.backend, 'model': self.model_name}

                executor_retry       = await self._get_executor(allowed_modules)
                messages_input_retry = self._build_messages_input(history, question, lang)
                timeout_retry        = _get_timeout(self.backend)

                try:
                    result   = await asyncio.wait_for(
                        executor_retry.ainvoke({'messages': messages_input_retry}, config=config),
                        timeout=timeout_retry,
                    )
                    answer   = result['messages'][-1].content
                    level    = detect_response_level(result)
                    duration = time.time() - start
                    msg_id   = await asyncio.to_thread(
                        self._history.save_message,
                        thread_id, 'assistant', answer,
                        level=level, backend=f'{self.backend}/{self.model_name}', duration=duration,
                    )
                    logger.info(f'[FALLBACK OK] {self.backend}/{self.model_name}')
                    return {'answer': answer, 'level': level, 'duration': duration,
                            'backend': self.backend, 'model': self.model_name, 'message_id': msg_id}
                except Exception as e2:
                    logger.error(f'[FALLBACK ERROR] {e2}')
                    return {'answer': _ui('service_unavailable', lang),
                            'level': 'error', 'duration': time.time() - start,
                            'backend': self.backend, 'model': self.model_name}

            logger.error(f'[ERROR] {err}')
            return {'answer': _ui('system_error', lang),
                    'level': 'error', 'duration': time.time() - start,
                    'backend': self.backend, 'model': self.model_name}

    async def _auto_title(self, thread_id: str, question: str):
        """Génère automatiquement un titre de conversation à partir de la première question."""
        try:
            from langchain_core.messages import HumanMessage
            # Prompt minimaliste — réduit les tokens et accélère la génération sur les modèles lents
            prompt   = f'5 words max, no quotes, title for: "{question[:80]}". Title only.'
            response = await asyncio.wait_for(
                self.llm.ainvoke([HumanMessage(content=prompt)]),
                timeout=45.0,
            )
            title = response.content.strip().strip('"').strip("'")[:60]
            if title:
                await asyncio.to_thread(self._history.update_thread_title, thread_id, title)
                logger.info(f'[AUTO-TITLE] {thread_id} → "{title}"')
        except Exception as e:
            logger.warning(f'[AUTO-TITLE] échec: {str(e)[:60]}')

    async def stream_process(
        self, question: str, thread_id: str,
        user_id: str = 'default_user',
        allowed_modules: list | None = None,
        lang: str = 'fr',
    ):
        """Générateur asynchrone d'événements SSE.

        Événements émis :
          {'type': 'thinking', 'data': '…'}
          {'type': 'tool',     'data': 'label outil'}
          {'type': 'chunk',    'data': 'token de texte'}
          {'type': 'done',     'level': '…', 'message_id': N, 'thread_id': '…'}
          {'type': 'error',    'data': 'message erreur'}
        """
        if not self._initialized:
            await self.initialize()

        start = time.time()

        # Feedback immédiat avant toute opération bloquante
        yield {'type': 'thinking', 'data': _ui('thinking', lang)}

        hist_limit = _HISTORY_LIMIT_BY_BACKEND.get(self.backend, _DEFAULT_HISTORY_LIMIT)
        await asyncio.to_thread(
            self._history.save_message, thread_id, 'user', question,
            content_normalized=question.strip().lower(), user_id=user_id,
        )
        history = await asyncio.to_thread(
            self._history.get_conversation_history, thread_id, limit=hist_limit
        )
        if len(history) > 1 and history[-1]['role'] == 'user':
            history = history[:-1]
        elif len(history) == 1 and history[-1]['role'] == 'user':
            history = []

        intent         = analyze_intent(question, history)
        hint           = _build_routing_hint(intent, history)
        messages_input = self._build_messages_input(history, question, lang, routing_hint=hint)
        executor       = await self._get_executor(allowed_modules)
        exec_thread_id = f'{thread_id}_{int(time.time() * 1000)}'
        config         = {'recursion_limit': _REACT_RECURSION_LIMIT,
                          'configurable': {'thread_id': exec_thread_id}}

        full_answer  = ''
        level        = 'knowledge'
        tool_results : list[tuple[str, str]] = []
        _sf          = _ThinkStreamFilter()
        try:
            _timeout = _get_timeout(self.backend)
            logger.debug(f'[STREAM] backend={self.backend} timeout={_timeout}s')
            async for event in _stream_with_timeout(
                executor.astream_events({'messages': messages_input}, config=config, version='v2'),
                _timeout,
            ):
                etype = event['event']
                if etype == 'on_tool_start':
                    tool_name = event.get('name', '')
                    label     = _tool_label(tool_name, lang)
                    yield {'type': 'tool', 'data': label, 'tool_name': tool_name}
                    level = 'data'

                elif etype == 'on_tool_end':
                    tool_name   = event.get('name', '')
                    output_data = event.get('data', {}).get('output', '')
                    raw_output  = _extract_tool_output(output_data)
                    if tool_name and raw_output:
                        tool_results.append((tool_name, raw_output))
                        logger.debug(f'[TOOL_END] {tool_name}: {raw_output[:80]}')

                elif etype == 'on_chat_model_stream':
                    chunk = event['data'].get('chunk')
                    if chunk and getattr(chunk, 'content', None):
                        visible = _sf.feed(chunk.content)
                        if visible:
                            full_answer += visible
                            yield {'type': 'chunk', 'data': visible}
            if not full_answer:
                # Le LLM n'a produit aucun texte (ex: tool non disponible, modèle muet).
                # Un retry direct avec un message d'explication simple.
                logger.warning('[STREAM] Réponse vide — retry texte sans outils')
                try:
                    _retry_msgs = self._build_messages_input(
                        history, question, lang,
                        routing_hint=(
                            'Réponds uniquement en texte, sans appeler d\'outil. '
                            'Si tu ne peux pas accéder aux données demandées, explique '
                            'poliment pourquoi et propose des alternatives disponibles.'
                        ),
                    )
                    # Nouvel executor sans outils pour forcer une réponse texte
                    _retry_exec = self._cra(
                        model=self.llm, tools=[],
                        prompt=self._cached_prompt,
                        checkpointer=MemorySaver(),
                    )
                    _retry_cfg  = {'recursion_limit': 4,
                                   'configurable': {'thread_id': f'{exec_thread_id}_empty_retry'}}
                    _sf_retry = _ThinkStreamFilter()
                    async for ev in _stream_with_timeout(
                        _retry_exec.astream_events({'messages': _retry_msgs}, config=_retry_cfg, version='v2'),
                        45.0,
                    ):
                        if ev['event'] == 'on_chat_model_stream':
                            ch = ev['data'].get('chunk')
                            if ch and getattr(ch, 'content', None):
                                visible = _sf_retry.feed(ch.content)
                                if visible:
                                    full_answer += visible
                                    yield {'type': 'chunk', 'data': visible}
                except Exception as _re:
                    logger.warning(f'[STREAM] retry vide échoué: {_re}')

                if not full_answer:
                    full_answer = _ui('no_answer', lang)
                    yield {'type': 'chunk', 'data': full_answer}

            duration              = time.time() - start
            clean_answer, qr_list = parse_quick_replies(full_answer)

            from mcp_client.chart_builder import build_charts
            from mcp_client.csv_export    import save_csv

            _tr          = list(tool_results)
            _wants_chart = bool(_CHART_RE.search(question))
            def _build_charts():
                if not _wants_chart:
                    return []
                charts = []
                for t_name, t_raw in _tr:
                    charts.extend(build_charts(t_name, t_raw))
                return charts

            try:
                msg_id, all_charts, csv_result = await asyncio.gather(
                    asyncio.to_thread(
                        self._history.save_message, thread_id, 'assistant', clean_answer,
                        level=level, backend=f'{self.backend}/{self.model_name}', duration=duration,
                    ),
                    asyncio.wait_for(asyncio.to_thread(_build_charts), timeout=30.0),
                    asyncio.wait_for(asyncio.to_thread(save_csv, clean_answer), timeout=15.0),
                )
            except asyncio.TimeoutError:
                logger.warning('[STREAM] chart/csv timeout — réponse envoyée sans graphique')
                msg_id      = None
                all_charts  = None
                csv_result  = None

            if not history:
                asyncio.create_task(self._auto_title(thread_id, question))

            if msg_id and all_charts:
                asyncio.create_task(asyncio.to_thread(
                    self._history.update_message_charts, msg_id, all_charts
                ))

            if csv_result:
                file_id, filename = csv_result
                yield {'type': 'file', 'file_id': file_id, 'filename': filename}

            # ── Génération PDF d'analyse à la demande ──────────────────────
            _PDF_RE = re.compile(
                r'\bpdf\b|rapport\s+pdf|en\s+pdf|au\s+format\s+pdf'
                r'|exporte[rz]?\s+(en\s+)?pdf|télécharge[rz]?\s+(le\s+)?rapport'
                r'|genere[rz]?\s+(un\s+)?(rapport|pdf)|génère[rz]?\s+(un\s+)?(rapport|pdf)',
                re.IGNORECASE,
            )
            _wants_pdf = bool(_PDF_RE.search(question)) and bool(all_charts)
            if _wants_pdf:
                from mcp_client.pdf_export import generate_analysis_pdf
                first_line = clean_answer.split('\n')[0].lstrip('#').strip()
                pdf_title  = first_line[:60] if first_line else 'Rapport ARIA'
                try:
                    pdf_result = await asyncio.wait_for(
                        asyncio.to_thread(
                            generate_analysis_pdf,
                            pdf_title, clean_answer, all_charts, lang, question,
                        ),
                        timeout=35.0,
                    )
                    if pdf_result:
                        pdf_id, pdf_filename = pdf_result
                        yield {'type': 'pdf_analysis', 'file_id': pdf_id, 'filename': pdf_filename}
                except asyncio.TimeoutError:
                    logger.warning('[STREAM] PDF generation timeout — ignoré')
                except Exception as _pe:
                    logger.error(f'[STREAM] PDF error: {_pe}', exc_info=True)

            yield {'type': 'done', 'level': level, 'thread_id': thread_id,
                   'message_id': msg_id, 'backend': f'{self.backend}/{self.model_name}',
                   'duration': round(duration, 2),
                   'quick_replies': qr_list or None,
                   'chart_data': all_charts or None}

        except Exception as e:
            err      = str(e)
            is_timeout = isinstance(e, asyncio.TimeoutError) or any(k in err.lower() for k in [
                'timeout', 'timed out', 'readtimeout', 'apitimeouterror',
            ])
            is_func_fail = any(k in err.lower() for k in [
                'failed to call a function', 'failed_generation',
            ])
            # Problème réseau pur : ne pas marquer les clés épuisées, juste changer de backend.
            is_connection_error = any(k in err.lower() for k in [
                'connection error', 'apiconnectionerror', 'connectionerror',
                'cannot connect', 'connection refused', 'unreachable',
            ])
            is_quota = is_timeout or is_func_fail or is_connection_error or any(k in err.lower() for k in [
                '413', 'too large', 'rate_limit', 'rate limit', '429',
                'resourceexhausted', 'resource exhausted', 'request limit',
                'limit reached', 'worker local',
            ])
            # Modèle surchargé (ex: Nvidia free tier via OpenRouter) ≠ clé épuisée.
            # Ne pas marquer la clé exhausted dans ce cas.
            is_model_overloaded = any(k in err.lower() for k in [
                'resourceexhausted', 'resource exhausted', 'request limit',
                'limit reached', 'worker local',
            ])

            if not is_quota:
                logger.error(f'[STREAM ERROR] {e}', exc_info=True)
                yield {'type': 'error', 'data': _ui('system_error', lang)}
                return

            log_reason = (
                'TIMEOUT'          if is_timeout          else
                'FUNC_FAIL'        if is_func_fail         else
                'CONNECTION_ERROR' if is_connection_error  else
                'MODEL_OVERLOADED' if is_model_overloaded  else
                'QUOTA/RATE'
            )
            logger.warning(f'[STREAM {log_reason}] Tentative de fallback LLM ({self.backend}/{self.model_name})')
            async with self._lock:
                try:
                    factory = LLMFactory()
                    if self.backend == 'groq':
                        if is_func_fail:
                            # JSON tool-call generation error: key is intact, try alternate Groq model first.
                            all_models = factory._collect_groq_models()
                            alt_models = [m for m in all_models if m != self.model_name]
                            switched = False
                            for alt_model in alt_models:
                                result = factory._try_groq(alt_model)
                                if result:
                                    self.llm, self.model_name, self.backend = result
                                    switched = True
                                    break
                            if not switched:
                                self.llm, self.model_name, self.backend = factory.create()
                        elif not is_timeout and not is_connection_error:
                            # True quota/rate-limit: mark key exhausted and switch backend.
                            # Connection errors leave the key intact.
                            current_key = factory.key_manager.get_groq_key(self.model_name)
                            if current_key:
                                factory.key_manager.mark_groq_exhausted(self.model_name, current_key)
                            self.llm, self.model_name, self.backend = factory.create()
                        else:
                            self.llm, self.model_name, self.backend = factory.create()
                    elif self.backend == 'openrouter':
                        # Only mark exhausted on a true key quota (429) —
                        # not on MODEL_OVERLOADED or connection errors (key is still valid).
                        if not is_timeout and not is_model_overloaded and not is_connection_error:
                            current_key = factory.key_manager.get_openrouter_key()
                            if current_key:
                                factory.key_manager.mark_openrouter_exhausted(current_key)
                        self.llm, self.model_name, self.backend = factory.create()
                    elif self.backend == 'cerebras':
                        current_key = factory.key_manager.get_cerebras_key()
                        # Timeout/connection error = transient — do not mark key exhausted.
                        if current_key and not is_timeout and not is_connection_error:
                            factory.key_manager.mark_cerebras_exhausted(current_key)
                        self.llm, self.model_name, self.backend = factory.create()
                    elif self.backend == 'ollama' and is_timeout:
                        # Retire ollama de l'ordre pour éviter la boucle infinie timeout → fallback → ollama → timeout
                        original_order = os.getenv('LLM_ORDER', '')
                        skip_order = ','.join(
                            b for b in original_order.split(',') if b.strip() != 'ollama'
                        )
                        os.environ['LLM_ORDER'] = skip_order
                        logger.warning(f'[STREAM TIMEOUT] Ollama ignoré pour fallback (ordre temp: {skip_order})')
                        try:
                            self.llm, self.model_name, self.backend = factory.create()
                        finally:
                            os.environ['LLM_ORDER'] = original_order
                    else:
                        self.llm, self.model_name, self.backend = factory.create()
                    self.executor = self._cra(
                        model=self.llm, tools=self.tools,
                        prompt=self._cached_prompt,
                        checkpointer=self._checkpointer,
                    )
                    self._invalidate_executor_cache()
                    logger.info(f'[STREAM FALLBACK] Nouveau backend: {self.backend}/{self.model_name}')
                except Exception:
                    logger.exception('[STREAM FALLBACK ERROR]')
                    yield {'type': 'error', 'data': _ui('service_unavailable', lang)}
                    return

            executor_fb    = await self._get_executor(allowed_modules)
            messages_fb    = self._build_messages_input(history, question, lang, routing_hint=hint)
            full_answer    = ''
            level          = 'knowledge'
            tool_results_fb: list[tuple[str, str]] = []
            _timeout_fb    = _get_timeout(self.backend)
            _sf_fb         = _ThinkStreamFilter()
            # CRITICAL: nouveau thread_id pour le nouvel executor — évite conflit MemorySaver
            config_fb      = {'recursion_limit': _REACT_RECURSION_LIMIT,
                              'configurable': {'thread_id': f'{exec_thread_id}_fb_{int(time.time()*1000)}'}}
            logger.info(f'[STREAM FALLBACK] backend={self.backend}/{self.model_name} timeout={_timeout_fb}s')
            try:
                async for event in _stream_with_timeout(
                    executor_fb.astream_events({'messages': messages_fb}, config=config_fb, version='v2'),
                    _timeout_fb,
                ):
                    etype = event['event']
                    if etype == 'on_tool_start':
                        tool_name = event.get('name', '')
                        yield {'type': 'tool', 'data': _tool_label(tool_name, lang)}
                        level = 'data'
                    elif etype == 'on_tool_end':
                        t_name = event.get('name', '')
                        t_raw  = _extract_tool_output(event.get('data', {}).get('output', ''))
                        if t_name and t_raw:
                            tool_results_fb.append((t_name, t_raw))
                    elif etype == 'on_chat_model_stream':
                        chunk = event['data'].get('chunk')
                        if chunk and getattr(chunk, 'content', None):
                            visible = _sf_fb.feed(chunk.content)
                            if visible:
                                full_answer += visible
                                yield {'type': 'chunk', 'data': visible}

                if not full_answer:
                    full_answer = _ui('no_response', lang)
                    yield {'type': 'chunk', 'data': full_answer}

                duration              = time.time() - start
                clean_answer, qr_list = parse_quick_replies(full_answer)

                from mcp_client.chart_builder import build_charts
                from mcp_client.csv_export    import save_csv

                _tr_fb       = list(tool_results_fb)
                _wants_chart = bool(_CHART_RE.search(question))
                def _build_charts_fb():
                    if not _wants_chart:
                        return []
                    charts = []
                    for t_n, t_r in _tr_fb:
                        charts.extend(build_charts(t_n, t_r))
                    return charts

                try:
                    msg_id, all_charts_fb, csv_fb = await asyncio.gather(
                        asyncio.to_thread(
                            self._history.save_message, thread_id, 'assistant', clean_answer,
                            level=level, backend=f'{self.backend}/{self.model_name}', duration=duration,
                        ),
                        asyncio.wait_for(asyncio.to_thread(_build_charts_fb), timeout=30.0),
                        asyncio.wait_for(asyncio.to_thread(save_csv, clean_answer), timeout=15.0),
                    )
                except asyncio.TimeoutError:
                    logger.warning('[STREAM FB] chart/csv timeout — réponse envoyée sans graphique')
                    msg_id       = None
                    all_charts_fb = None
                    csv_fb       = None

                if msg_id and all_charts_fb:
                    asyncio.create_task(asyncio.to_thread(
                        self._history.update_message_charts, msg_id, all_charts_fb
                    ))

                if csv_fb:
                    fid, fname = csv_fb
                    yield {'type': 'file', 'file_id': fid, 'filename': fname}

                yield {'type': 'done', 'level': level, 'thread_id': thread_id,
                       'message_id': msg_id, 'backend': f'{self.backend}/{self.model_name}',
                       'duration': round(duration, 2),
                       'quick_replies': qr_list or None,
                       'chart_data': all_charts_fb or None}
            except Exception as e2:
                err2      = str(e2)
                timeout2  = isinstance(e2, asyncio.TimeoutError) or any(
                    k in err2.lower() for k in ['timeout', 'timed out', 'readtimeout', 'apitimeouterror']
                )
                logger.warning(f'[STREAM FALLBACK ERROR] timeout={timeout2} backend={self.backend}/{self.model_name} err={err2[:120]}')

                if not (timeout2 and self.backend == 'ollama'):
                    err_msg = (_ui('analysis_too_long', lang)
                               if timeout2 else _ui('service_unavailable', lang))
                    yield {'type': 'error', 'data': err_msg}
                    return

                # Ollama timeout au retry → dernier recours sans Ollama
                logger.warning('[STREAM RETRY TIMEOUT] Ollama trop lent, dernier recours…')
                async with self._lock:
                    try:
                        orig_order = os.getenv('LLM_ORDER', '')
                        no_ollama  = ','.join(b for b in orig_order.split(',') if b.strip() != 'ollama')
                        os.environ['LLM_ORDER'] = no_ollama
                        try:
                            factory_lr = LLMFactory()
                            self.llm, self.model_name, self.backend = factory_lr.create()
                            self.executor = self._cra(
                                model=self.llm, tools=self.tools,
                                prompt=self._cached_prompt, checkpointer=self._checkpointer,
                            )
                            self._invalidate_executor_cache()
                            logger.info(f'[STREAM LAST RESORT] {self.backend}/{self.model_name}')
                        finally:
                            os.environ['LLM_ORDER'] = orig_order
                    except Exception as lr_err:
                        logger.error(f'[STREAM LAST RESORT ERROR] {lr_err}')
                        yield {'type': 'error', 'data': _ui('service_unavailable', lang)}
                        return

                executor_lr  = await self._get_executor(allowed_modules)
                messages_lr  = self._build_messages_input(history, question, lang)
                full_lr      = ''
                config_lr    = {'recursion_limit': _REACT_RECURSION_LIMIT,
                                'configurable': {'thread_id': f'{exec_thread_id}_lr_{int(time.time()*1000)}'}}
                try:
                    async for event in executor_lr.astream_events(
                        {'messages': messages_lr}, config=config_lr, version='v2'
                    ):
                        if event['event'] == 'on_chat_model_stream':
                            chunk = event['data'].get('chunk')
                            if chunk and getattr(chunk, 'content', None):
                                full_lr += chunk.content
                                yield {'type': 'chunk', 'data': chunk.content}
                    if not full_lr:
                        full_lr = _ui('no_response', lang)
                        yield {'type': 'chunk', 'data': full_lr}
                    dur_lr       = time.time() - start
                    clean_lr, qr_lr = parse_quick_replies(full_lr)
                    mid_lr = self._history.save_message(
                        thread_id, 'assistant', clean_lr,
                        level=level, backend=f'{self.backend}/{self.model_name}', duration=dur_lr,
                    )
                    yield {'type': 'done', 'level': level, 'thread_id': thread_id,
                           'message_id': mid_lr, 'backend': f'{self.backend}/{self.model_name}',
                           'duration': round(dur_lr, 2), 'quick_replies': qr_lr or None, 'chart_data': None}
                except Exception as e3:
                    logger.error(f'[STREAM LAST RESORT RETRY ERROR] {e3}')
                    yield {'type': 'error', 'data': _ui('service_unavailable', lang)}

    # Ordre de priorité des backends (doit correspondre à LLM_ORDER dans .env)
    _BACKEND_PRIORITY = ['openrouter', 'groq', 'cerebras', 'ollama', 'gemini', 'huggingface']

    async def _auto_ping(self):
        """Tâche de fond : toutes les heures, teste si un meilleur backend est disponible
        et bascule automatiquement vers lui (ex. OpenRouter après reset quota journalier)."""
        await asyncio.sleep(3600)  # 1ère vérification après 1h
        while True:
            try:
                await self._try_upgrade_backend()
            except Exception as e:
                logger.debug(f'[AUTO-PING] erreur: {e}')
            await asyncio.sleep(3600)

    async def _try_upgrade_backend(self):
        """Teste les backends de priorité supérieure au backend actuel.
        Si l'un d'eux répond, bascule dessus et met à jour le cache de clés."""
        current_rank = self._BACKEND_PRIORITY.index(self.backend) \
                       if self.backend in self._BACKEND_PRIORITY else len(self._BACKEND_PRIORITY)
        if current_rank == 0:
            logger.debug('[AUTO-PING] déjà sur le meilleur backend')
            return

        factory = LLMFactory()
        better_backends = self._BACKEND_PRIORITY[:current_rank]

        for backend_name in better_backends:
            # Réinitialise temporairement les clés épuisées de ce backend pour re-tester
            factory.key_manager.state[backend_name]['exhausted'] = [] \
                if backend_name in factory.key_manager.state else []

            try_fn = {
                'ollama'     : factory._try_ollama_all,
                'cerebras'   : factory._try_cerebras,
                'openrouter' : factory._try_openrouter,
                'gemini'     : factory._try_gemini,
                'groq'       : factory._try_groq_all,
                'huggingface': factory._try_huggingface,
            }.get(backend_name)

            if not try_fn:
                continue

            result = await asyncio.to_thread(try_fn)
            if not result:
                logger.debug(f'[AUTO-PING] {backend_name} encore indisponible')
                continue

            llm, model, backend = result
            async with self._lock:
                self.llm, self.model_name, self.backend = llm, model, backend
                self.executor = self._cra(
                    model=self.llm, tools=self.tools,
                    prompt=self._cached_prompt,
                    checkpointer=self._checkpointer,
                )
                self._invalidate_executor_cache()
                factory.key_manager.save()
            logger.info(f'[AUTO-PING] ✓ Upgrade automatique → {backend}/{model}')
            return

    async def refresh_context(self):
        """Recharge le prompt depuis MySQL et invalide tout le cache d'executors."""
        if not self._initialized:
            return
        async with self._lock:
            logger.info('Rafraîchissement contexte...')
            self._cached_prompt = build_full_prompt(force_refresh=True)
            self.executor = self._cra(
                model=self.llm, tools=self.tools,
                prompt=self._cached_prompt,
                checkpointer=self._checkpointer,
            )
            self._invalidate_executor_cache()
            logger.info('Contexte rafraîchi')
