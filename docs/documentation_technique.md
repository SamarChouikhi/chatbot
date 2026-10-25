# ARIA — Documentation technique (Angular / Python / Quarkus / ML)

> Document de référence technique pour le rapport de PFE. Couvre les quatre composantes du système : frontend Angular, backend applicatif Python (FastAPI + agent LLM), backend métier Java Quarkus, et le module ML de détection d'anomalies (AD).

---

## 1. Frontend — Angular

### 1.1 Stack technique

| Élément | Version |
|---|---|
| Angular (core, forms, router, animations...) | 16.2.x |
| TypeScript | 5.1.x |
| RxJS | 7.8.x |
| Zone.js | 0.13.x |
| Chart.js | 4.4.x |
| ngx-translate (core + http-loader) | 15.x / 8.x |
| ngx-markdown | 16.x |
| jsPDF + jspdf-autotable | 4.x / 5.x |
| Karma + Jasmine (tests) | 6.4.x / 4.6.x |

Port de dev : `4200` (`ng serve`). Build de production via `ng build`. Vérification de types sans émission : `npx tsc --noEmit`.

### 1.2 Architecture applicative

- **Structure modulaire par domaine métier** : `electricity/`, `water/`, `gaz/`, `device-detail/`, `chatbot/`, chacun avec son `component.ts/html/scss`.
- **Couche services** (`src/app/services/`, 22+ fichiers) : un service Angular par domaine (aria, auth, analytics, energy, water, gaz, fuel, pdf-report, etc.), responsable des appels HTTP vers les deux backends (Java Quarkus `:8080` pour le CRUD métier/auth, FastAPI `:8001` pour le chatbot IA).
- **Guards** (`core/guards/`) : `auth.guard.ts` (vérifie la présence/validité du JWT), `role.guard.ts` (contrôle d'accès par rôle/module autorisé — aligné sur `allowed_modules` côté backend).
- **Interceptor** (`core/interceptors/auth.interceptor.ts`) : injecte automatiquement le JWT (`Authorization: Bearer <token>`) sur chaque requête HTTP sortante.
- **Chatbot UI** (`chatbot/`) : consomme le flux SSE (`GET /chat/stream`) exposé par FastAPI, avec rendu progressif token-par-token (phases *thinking* / *tool* / *chunk*), rendu Markdown (ngx-markdown) et quick-replies.
- **Génération de rapports** : `pdf-report.service.ts` compose des exports PDF côté client via jsPDF/autotable à partir des données agrégées reçues des API.
- **Graphiques** : Chart.js pour les séries temporelles de consommation (énergie L1/L2/L3, eau, gaz, carburant) et les visualisations d'anomalies.

### 1.3 Internationalisation

Toutes les chaînes UI passent par des clés `ngx-translate`, définies dans `src/assets/i18n/{fr,ar,en}.json`. Aucune chaîne n'est codée en dur dans les templates.

### 1.4 Flux de communication

```
Angular (4200)
 ├─ HTTP REST  → Quarkus (8080)   : auth, CRUD device/KPI/electricity/water/gaz/fuel/alerts
 ├─ HTTP POST  → FastAPI (8001)   : /chat (réponse JSON complète)
 ├─ SSE        → FastAPI (8001)   : /chat/stream (streaming token par token)
 └─ SSE        → Quarkus (8080)   : AlertSseBroadcaster (push d'alertes temps réel)
```

---

## 2. Backend applicatif — Python / FastAPI (agent conversationnel)

### 2.1 Stack technique

| Élément | Version |
|---|---|
| Python | 3.13 |
| FastAPI | 0.135.1 |
| Uvicorn (ASGI) | 0.41.0 |
| LangGraph (boucle agentique ReAct) | 1.1.2 |
| LangChain core | 1.4.8 |
| langchain-mcp-adapters | 0.2.1 |
| MCP (Model Context Protocol) | 1.26.0 |
| SQLAlchemy | 2.0.48 |
| PyMySQL | 1.1.2 |
| APScheduler | 3.11.0 |
| Pydantic / pydantic-settings | 2.12.5 / 2.13.1 |
| sse-starlette | 3.3.2 |
| Connecteurs LLM : `groq`, `google-genai`, `langchain-groq`, `langchain-google-genai`, `langchain-openai`, `langchain-huggingface`, `langchain-ollama` | multi-fournisseur |

Ports : application principale `8001`, serveur MCP `8000` (SSE). Le serveur MCP **doit** démarrer avant l'application FastAPI (`AriaAgent.initialize()` se connecte au endpoint SSE au démarrage ; en cas d'échec, l'app démarre en mode dégradé `agent_ready=False`).

### 2.2 Architecture MCP (Model Context Protocol)

Le système est découpé en deux processus communicants via **MCP over SSE** :

- **MCP Server** (`mcp_server/`) : expose **17 tools** typés (accès base de données, analyses par domaine, détection d'anomalies, prédictions, recommandations) organisés en 9 modules (`database.py`, `sensors.py`, `alerts.py`, `anomaly.py`, `predictions.py`, `ad_analysis.py`, `reco_tool.py`, `utils.py`, `_helpers.py`).
- **MCP Client / Agent** (`mcp_client/agent.py`) : `AriaAgent`, boucle ReAct implémentée avec LangGraph, instanciée en singleton dans le `lifespan` FastAPI (survit au hot-reload).

**Filtrage dynamique des outils** : chaque utilisateur possède un champ `allowed_modules` (table `aria_employees`). `_TOOL_MODULE_MAP` associe chaque tool MCP à un module requis (ex. `energy_analysis` → `énergie électrique`) ; les tools non mappés (`None`) sont toujours disponibles. Ajouter un tool exige une entrée dans cette map.

**Limite de récursion ReAct** : `_REACT_RECURSION_LIMIT = 16` (1 appel d'outil = 2 étapes AI+Tool), soit jusqu'à 7 appels d'outils par tour (9 pour la chaîne *FULL REPORT*, grâce au batching).

### 2.3 Orchestration multi-LLM

`mcp_client/llm_factory.py` implémente un routage `auto` sur plusieurs backends (Cerebras, Groq, Gemini, OpenRouter, Ollama, HuggingFace), avec ordre de repli configurable (`LLM_ORDER`). `KeyStateManager` gère la **rotation de clés API multiples** par fournisseur (`PREFIX_API_KEY_1`…`_9`) et persiste l'état des clés épuisées dans `.key_state.json` entre redémarrages.

Contraintes par backend (timeout / longueur d'historique conservée) :

| Backend | Timeout | Historique (car.) | Historique (msg) |
|---|---|---|---|
| Ollama | 180 s | 1200 | 15 |
| OpenRouter | 150 s | 1000 | 12 |
| HuggingFace | 120 s | 800 | 8 |
| Groq | 120 s | 600 | 8 |
| Gemini | 120 s | 1000 | 12 |
| Cerebras | 120 s | 800 | 10 |

### 2.4 Pipeline de traitement d'une requête chat

```
Requête utilisateur
 → intents.py       : détection d'intents statiques (salutations, aide) — répond sans appel LLM
 → preprocessor.py   : analyse (type de capteur, période, type de requête, is_data_query)
 → AriaAgent (LangGraph) : sélection et appel des tools MCP pertinents
 → output_guard.py   : scoring qualité [0–1] sur 4 dimensions pondérées
      - tools_called_ok (45%) — outils MCP effectivement invoqués pour une requête data
      - length_ok (25%)       — longueur adaptée (≥15 mots si data, ≤120 mots si simple)
      - is_clean (20%)        — absence de signaux d'hallucination ([value], placeholder, {{}}…)
      - has_units (10%)       — unités techniques présentes (kWh, m³, °C…)
   → RETRY_THRESHOLD = 0.60 : un seul retry automatique si score < seuil
     (score plafonné à 0.55 si tools_called_ok=False OU is_clean=False → retry garanti)
 → StreamingResponse (SSE token par token, jamais bufferisé en entier)
```

### 2.5 Ordonnancement (APScheduler) — 5 jobs

| Horaire (UTC) | Job | Rôle |
|---|---|---|
| 01:00 | Replay historique + `archive_sync` | Recharge les données passées dans `daily_*`, reconstruit les agrégats mensuels (`archive_*_m`) pour le dashboard Java |
| 02:00 (dimanche) | Audit de stratégie | Détecte les devices ColdStart ayant assez d'historique (`_HOT_MIN_DAYS`) pour être promus HotStart |
| 03:00 | Pipeline quotidien | Extraction 96h → agrégation horaire idempotente (`ON DUPLICATE KEY UPDATE`) → détection HotStart → log dans `pipeline_runs` |
| 04:00 | Cycle de recommandations IA | Baselines, génération LLM, mesure ROI (48h post-acceptation) |
| Toutes les 2h | Vérification proactive | Scan `ad_results` / `aria_predictions`, notifications SSE (cooldown 24h par utilisateur/domaine) |

Au démarrage, si `daily_*` est jugé périmé (> 2 jours), un backfill de 30 jours + une exécution AD sont déclenchés automatiquement (même thread, séquentiel).

### 2.6 Sécurité et robustesse

- **Garde-fou SQL** (`mcp_server/db/connection.py`) : rejet de toute requête contenant un mot-clé destructif (`DROP`, `DELETE`, `TRUNCATE`…) avant exécution — le tool `execute_query` est lecture seule par construction.
- **Pool de connexions** : `QueuePool` (taille 5, `max_overflow=10`).
- **Rate limiting** : `api/helpers.py:rate_ok()` — 30 requêtes/min par IP, HTTP 429 au-delà.
- **CORS** : piloté par `CORS_ORIGINS` (env var), `*` par défaut en dev.
- **Documentation API** : Swagger (`/docs`), ReDoc (`/redoc`) et `/openapi.json` désactivés automatiquement si `ENV=prod`.
- **Historique de conversation** : `MySQLHistoryManager` auto-crée `chat_threads`/`chat_messages` au démarrage ; bascule en liste mémoire si MySQL est injoignable.
- **Session** : map en mémoire (`api/session.py`), TTL 4h d'inactivité, non persistante (perdue au redémarrage).

### 2.7 Multimodal

- `/vision` (`vision.py`) : analyse d'image via Groq multimodal, avec clé dédiée `VISION_API_KEY_1` (repli sur le pool `GROQ_API_KEY_N`).
- `/transcribe` (`transcribe.py`) : transcription vocale via AssemblyAI.

---

## 3. Backend métier — Java / Quarkus

### 3.1 Stack technique

| Élément | Version |
|---|---|
| Quarkus (BOM) | 3.15.1 |
| Java | 17 (`maven.compiler.release`) |
| RESTEasy Reactive + Jackson | via BOM |
| Hibernate ORM Panache | via BOM |
| Quarkus JDBC MySQL | via BOM |
| SmallRye JWT (+ build) | via BOM |
| Quarkus Scheduler | via BOM |
| Quarkus Mailer | via BOM |
| Twilio SDK | 9.10.0 |
| jBCrypt | 0.4 |
| Tests : JUnit5 (quarkus-junit5), Mockito 5.12.0, AssertJ 3.26.3 | |

Mode dev avec hot-reload : `mvn quarkus:dev`. Build production : `mvn clean package` → `target/backbws-1.0-SNAPSHOT-runner.jar`. Port : `8080`.

### 3.2 Architecture en couches

- **`resource/`** (14 endpoints REST) : Auth, Device, KPI, Electricity, Water, Gaz, Fuel, Alerts, AlertSseBroadcaster, Chat, Recovery, Role, User.
- **`service/`** (15 classes) : logique métier par domaine + services transverses `JwtService`, `TwilioService`, `WaterArchiveJob`.
- **`dto/`** : objets de requête/réponse découplés des entités JPA.
- **`entity/`** : entités JPA mappées sur le schéma `bw_samar`.
- **`util/`** : helpers JWT.

`quarkus.hibernate-orm.database.generation=none` : **aucune migration automatique** — le schéma MySQL doit préexister (créé via `seed_data.sql` / `chatbot/data_seed.sql`).

### 3.3 Authentification

```
Angular → POST /login (Quarkus :8080)
        → JWT RS256, TTL 1h ; refresh token 7 jours
        → issuer: https://ioit.bws.com
        → clés : META-INF/resources/{publicKey,privateKey}.pem
```

Chaque requête protégée passe par l'intercepteur Angular qui attache le token ; côté serveur, SmallRye JWT valide la signature RS256 contre la clé publique.

### 3.4 Temps réel et notifications

- **`AlertSseBroadcaster`** : diffusion SSE des alertes vers les clients Angular connectés.
- **Notifications externes** : `TwilioService` (SMS + WhatsApp) et Quarkus Mailer (SMTP, mode `MAILER_MOCK=true` en dev pour dry-run).

### 3.5 Configuration notable

Pool de connexions défini directement dans `application.properties` (pas via env vars) :

```properties
max-size=30
min-size=5
acquisition-timeout=30
max-lifetime=PT30M
```

CORS hardcodé sur `http://localhost:4200` (à adapter en production).

---

## 4. Machine Learning — Détection d'anomalies (module AD)

### 4.1 Stack technique

| Élément | Rôle |
|---|---|
| `torch` | Backend d'inférence/fine-tuning pour le modèle de fondation |
| `chronos-forecasting` | Modèle de séries temporelles pré-entraîné (Amazon Chronos), fine-tuné par device |
| `pandas` / `numpy` | Manipulation des séries temporelles |
| `pymysql` | Accès direct MySQL pour l'entraînement/l'inférence |
| `pyyaml` | Configuration par domaine (`config.yaml`) |
| `matplotlib` | Génération de graphiques de diagnostic (désactivable via `--no-plots`) |

### 4.2 Stratégie à deux régimes : HotStart / ColdStart

Le routage est automatique, basé sur le volume d'historique disponible par device :

```
AD/main.py → AD/runner.py
  si historique device > 720 lignes (≈ 30 jours) → HotStart
  sinon                                            → ColdStart
```

**Isolation des processus** : `runner.py` exécute HotStart et ColdStart comme **sous-processus séparés** (jamais dans le même processus) pour éviter les conflits d'import PyTorch/scikit-learn.

#### HotStart (`AD/HotStart/`)

- Modèle de fondation **Chronos** fine-tuné par device (transfer learning sur séries temporelles).
- Détection par **analyse des résidus** (écart entre valeur observée et prédiction du modèle), avec bornes `q10`/`q90` stockées dans `ad_results`.
- Fine-tuning déclenché via `--retrain` (puis détection) ou `--retrain-only`.
- Ré-entraînement mensuel indépendant : `AD/HotStart/common/monthly_retrainer.py`.

#### ColdStart (`AD/ColdStart/`)

- Pour les nouveaux devices sans historique suffisant.
- Méthodes statistiques classiques : **Z-score, IQR, Isolation Forest, approche d'ensemble**.
- Génération de données synthétiques (`synthetic_generator.py`) pour amorcer la détection en l'absence d'historique réel, avec injection d'anomalies traçables (`is_injected_anomaly`).
- Promotion automatique vers HotStart via l'audit de stratégie hebdomadaire (dimanche 02:00 UTC) dès que le seuil `_HOT_MIN_DAYS` de jours distincts en base est atteint.

### 4.3 Ré-entraînement mensuel de Chronos

Intégré pour les domaines **energy** et **water** uniquement (`gaz`/`fuel` n'ont pas de section `retraining` dans leur config).

- Déclenché manuellement via `--retrain` (fine-tuning puis détection) ou `--retrain-only`.
- Un fine-tuning par device et par nouveau mois de données, jusqu'à M12 (device alors « mature », plus de ré-entraînement).
- Chaque device est fine-tuné à partir des poids de base de Chronos (restaurés entre deux devices).
- Split temporel 80/20, AdamW (lr `1e-4`, weight decay `1e-2`), gradient clipping à 1.0, 3 epochs ; `train_loss`/`val_loss` par epoch persistés dans `<device>_m<NN>_metrics.json`.
- Le nouveau checkpoint remplace l'ancien ; l'état par device est conservé dans `retrain_state.json`. En cas d'échec du fine-tuning, l'état n'avance pas et le mois est retenté au prochain run.

### 4.4 Configuration par domaine

Chaque domaine (`energy`, `water`, `gaz`, `fuel`) possède son propre `AD/<domaine>/config.yaml` définissant : algorithme(s), seuils, phases (énergie : L1/L2/L3), et pour `energy`/`water`, le bloc `retraining:` (`actif`, `epochs`, `taux_apprentissage`, checkpoints, fichier d'état).

### 4.5 Évaluation et calibration

`AD/eval/coldstart_calibration.py` exécute le pipeline de production réel (`ColdStart/main.py --synthetic-only`, via subprocess, à l'image de `ad_runner.py`) et confronte les anomalies injectées (`is_injected_anomaly`) aux anomalies détectées pour calculer **précision / rappel / F1**, moyennés sur plusieurs graines aléatoires.

```bash
python eval/coldstart_calibration.py --population-dir /path/to/population/csvs
python eval/coldstart_calibration.py --domains fuel gaz --seeds 5
python eval/coldstart_calibration.py --min-precision 0.85 --min-recall 0.60
```

Utilisé après toute modification d'un seuil, d'un algorithme ou du générateur synthétique, pour détecter une régression de calibration. `ColdStart/main.py --seed N` permet la reproductibilité (override de `synthese.graine`).

### 4.6 Intégration au pipeline applicatif

`chatbot/bws_pfe/api/pipeline/ad_runner.py` fait le pont entre le scheduler FastAPI et le module `AD/` : déclenche la détection HotStart par domaine (subprocess) et écrit les résultats dans `ad_results`. Les résultats alimentent ensuite :
- le tool MCP `ad_analysis` / `anomaly_detection` (exposés à l'agent conversationnel),
- le moteur de recommandations (`recommendation_engine.py`) qui enrichit ses baselines P10/P50/P90 avec les scores Chronos,
- les notifications proactives (`proactive.py`) diffusées en SSE.

---

## 5. Synthèse des flux inter-services

```
┌─────────────┐   REST (JWT)   ┌──────────────┐        JDBC        ┌───────────┐
│  Angular     │───────────────▶│  Quarkus      │────────────────────▶│  MySQL    │
│  (4200)      │◀───────────────│  (8080)       │                     │ bw_samar  │
└─────┬────────┘   SSE alerts  └──────────────┘                     └─────┬─────┘
      │                                                                    │
      │  REST + SSE (chat)                                        SQLAlchemy/PyMySQL
      ▼                                                                    │
┌─────────────┐   MCP over SSE  ┌──────────────┐                          │
│  FastAPI     │────────────────▶│  MCP Server   │──────────────────────────┘
│  (8001)      │◀────────────────│  (8000)       │
└─────┬────────┘                └──────────────┘
      │ subprocess (import isolé)
      ▼
┌─────────────────────────────┐
│  AD (HotStart / ColdStart)   │
│  Chronos / stats classiques  │
└─────────────────────────────┘
```

---

*Document généré à partir de l'état du code au 2026-09-23 (branche `FinalVersion`). À maintenir en synchronisation avec `CLAUDE.md` en cas d'évolution d'architecture.*
