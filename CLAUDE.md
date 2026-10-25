# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ARIA** (Adaptive Real-time IoT Analytics) — An IoT monitoring and anomaly detection platform for smart building management (BMS). Tracks energy, water, gas, and fuel consumption with an AI-powered chatbot for natural language queries.

## Services & Ports

| Service | Stack | Port | Path |
|---|---|---|---|
| Angular Frontend | Angular 16, TypeScript | 4200 | `chatbot/ioitfr/` |
| FastAPI App | Python 3.13, FastAPI | 8001 | `chatbot/bws_pfe/` |
| MCP Server | Python, FastAPI, SSE | 8000 | `chatbot/bws_pfe/mcp_server/` |
| Java Backend | Quarkus 3, Java 17 | 8080 | `chatbot/backbws/` |
| MySQL | Database | 3306 | `bw_samar` schema |

> **Note**: The actual FastAPI application lives in `chatbot/bws_pfe/`. A root-level `bws_pfe/` directory may appear in older checkouts — it was a backward-compatibility shim and is no longer present.

## Build & Run Commands

### FastAPI App (Python 3.13 — ports 8001 & 8000)
```bash
cd chatbot/bws_pfe
pip install -r requirements.txt
python mcp_server/main.py         # Start MCP server FIRST (on :8000)
python aria_api.py                # Then start app (on :8001)
```

> **Startup order**: the MCP server must be running before the FastAPI app starts. `AriaAgent.initialize()` connects to the MCP SSE endpoint at startup; if it fails, the app starts in degraded mode (`agent_ready=False`) serving only static intents.

### Java Backend (Quarkus)
```bash
cd chatbot/backbws
mvn quarkus:dev                   # Dev mode with hot-reload
mvn clean package                 # Production build
java -jar target/backbws-1.0-SNAPSHOT-runner.jar
```

### Angular Frontend
```bash
cd chatbot/ioitfr
npm install
ng serve                          # http://localhost:4200
ng build                          # Production build
npm test                          # Karma + Jasmine
npx tsc --noEmit                  # type-check without emitting
```

### Anomaly Detection (AD) Modules
```bash
cd AD

# Unified entry point — auto-routes each device to HotStart or ColdStart
# based on historical data volume (threshold: 720 rows = 30 days)
python main.py --domain energy --data /path/to/energy.csv
python main.py --domain water  --data water.csv --no-plots     # skip PNG generation
python main.py --domain energy --device cuda --retrain         # with Chronos fine-tuning

# HotStart only (Chronos-based, devices with > 720 rows of history)
python HotStart/main.py --domain energy                        # detect only
python HotStart/main.py --domain energy --retrain              # fine-tune then detect
python HotStart/main.py --domain energy --retrain-only         # fine-tune only

# ColdStart only (new devices with ≤ 720 rows)
python ColdStart/main.py --domain energy --device NEW_DEVICE_002 --phases L1 L2 L3
python ColdStart/main.py --domain water
```

### Monthly Chronos fine-tuning

`AD/HotStart/common/monthly_retrainer.py` (invoked via `--retrain`/`--retrain-only`) fine-tunes Chronos per device once per new month of data, up to M12 (then the device is marked mature and never retrained) — wired for `energy` and `water` only (`gaz`/`fuel` configs have no `retraining:` block). Each device is fine-tuned from the base weights (restored between devices in `retrain_job.py`); the new checkpoint is adopted unconditionally and the per-device state is persisted in `retrain_state.json`. Not scheduled: run it manually.

### ColdStart Calibration Check
```bash
cd AD
python eval/coldstart_calibration.py --population-dir /path/to/population/csvs
python eval/coldstart_calibration.py --domains fuel gaz --seeds 5
python eval/coldstart_calibration.py --min-precision 0.85 --min-recall 0.60
```
Runs the real production pipeline (`ColdStart/main.py --synthetic-only`, via subprocess like `ad_runner.py`) per domain and cross-references each run's injected-anomaly ground truth (`is_injected_anomaly` column) against detected anomalies to compute precision/recall/F1, averaged over seeds. Use after changing a threshold, algorithm, or the synthetic generator to catch calibration regressions. Requires a real population CSV per domain (not included in the repo, passed via `--population-dir`/`--population-map`) to seed realistic synthetic stats. `ColdStart/main.py --seed N` overrides `synthese.graine` for reproducible synthetic runs and exists mainly to support this script.

### Python Tests
```bash
cd chatbot/bws_pfe
pytest tests/                     # unit tests
pytest tests/test_helpers.py      # single test file

cd AD
pytest tests/                     # AD threshold/routing tests
```

Pytest config is in `pytest.ini` (async mode: `auto`). `tests/conftest.py` pre-sets minimal env vars (`DB_PASSWORD` required; all others have defaults) so tests import cleanly without a real `.env`. AD has its own `pytest.ini` with the same structure.

### Import CSV → MySQL

```bash
# Via CLI standalone (depuis le répertoire AD)
cd AD
python import_to_db.py --domain energy --data /path/to/energy.csv
python import_to_db.py --domain water  --data water.csv
python import_to_db.py --all           # importe les 4 CSV depuis les config.yaml AD

# Via API (FastAPI sur :8001)
POST /system/import-csv      {"domain": "energy", "csv_path": "/path/to/energy.csv"}
POST /system/import-all-csv  # lit les chemins dans AD/HotStart/<domain>/config.yaml
```

Après import, le pipeline AD lit directement depuis `daily_*` via `ad_runner.py`.

### Manual AD Trigger (bypass scheduler)
```bash
cd chatbot/bws_pfe
python run_ad_now.py                          # all 4 domains
python run_ad_now.py --domain energy water    # specific domains
```
Reads from `daily_*` tables directly (same as scheduler job) — requires `.env` and MySQL.

### Evaluation Framework
```bash
cd chatbot/bws_pfe
python -m eval.runner             # runs all EvalCases against the live agent
```

## Environment Variables

Copy `.env.example` → `.env` in `chatbot/bws_pfe/`. Key variables:

| Variable | Default | Purpose |
|---|---|---|
| `DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD` | `localhost/3306/bw_samar/root/—` | MySQL connection |
| `API_PORT` | `8001` | FastAPI listen port |
| `MCP_SERVER_URL` | `http://localhost:8000/sse` | MCP server endpoint |
| `LLM_BACKEND` | `auto` | `auto \| cerebras \| groq \| gemini \| openrouter \| ollama \| huggingface` |
| `LLM_ORDER` | `cerebras,openrouter,groq,gemini,ollama,huggingface` | Fallback order for `auto` mode |
| `GROQ_API_KEY_1` … `_9` | — | Comma-separated keys; `KeyStateManager` rotates and persists exhausted keys to `.key_state.json` |
| `GROQ_MODEL_1/2/3` | `llama-3.3-70b-versatile`, `qwen/qwen3-32b`, `llama-3.1-8b-instant` | Groq model rotation (GROQ_MODEL_1 is the primary capable model; GROQ_MODEL_3 is the fast/cheap fallback) |
| `GROQ_TEMPERATURE` | `0` | Groq inference temperature |
| `GEMINI_API_KEY_1` … | — | Gemini keys (same `_1`…`_9` rotation pattern as Groq) |
| `GEMINI_MODEL` | `gemini-2.0-flash` | |
| `CEREBRAS_API_KEY_1` … | — | Cerebras keys |
| `CEREBRAS_MODEL` | `gpt-oss-120b` | |
| `OPENROUTER_API_KEY_1` … | — | OpenRouter keys |
| `OPENROUTER_MODEL` | `nvidia/nemotron-3-super-120b-a12b:free` | |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | |
| `OLLAMA_MODEL_1/2` | `qwen2.5:14b`, `qwen2.5:7b` | Ollama model rotation |
| `OLLAMA_TIMEOUT` | `300` | |
| `HF_API_KEY_1` … | — | HuggingFace keys |
| `HF_MODEL` | `Qwen/Qwen3-8B` | HuggingFace model |
| `VISION_API_KEY_1`, `VISION_MODEL` | — / `qwen/qwen3.6-27b` | Image analysis (multimodal Groq; falls back to `GROQ_API_KEY_N` pool if unset) |
| `ASSEMBLYAI_API_KEY` | — | Voice transcription |
| `CORS_ORIGINS` | `*` | FastAPI CORS; set to exact origin URLs in production |
| `LOG_LEVEL` | `INFO` | |
| `ENV` | `dev` | |
| `REPLAY_HOUR_UTC` | `1` | Hour (UTC) for the daily data-replay job |
| `REPLAY_MINUTE_UTC` | `0` | Minute for the daily data-replay job |

Java backend vars (in `application.properties`):

| Variable | Default | Purpose |
|---|---|---|
| `DB_URL` | `jdbc:mysql://localhost:3306/bw_samar?serverTimezone=UTC` | Full JDBC URL |
| `DB_USER / DB_PASSWORD` | `root / admin` | DB credentials |
| `JWT_ISSUER` | `https://ioit.bws.com` | JWT issuer claim |
| `CORS_ORIGINS` | `http://localhost:4200` | Java CORS allowed origin |
| `TWILIO_SID / TWILIO_TOKEN` | — | Twilio account credentials (SMS alerts) |
| `TWILIO_WA_NUMBER` | `whatsapp:+14155238886` | WhatsApp sender |
| `TWILIO_SMS_NUMBER` | `+14155238886` | SMS sender |
| `MAILER_FROM / MAILER_USER / MAILER_PASSWORD` | `chouikhisamar93@gmail.com / — / —` | SMTP credentials |
| `MAILER_HOST / MAILER_PORT` | `smtp.gmail.com / 587` | SMTP server |
| `MAILER_MOCK` | `true` | Dry-run email in dev; set `false` for real sends |

Connection pool is configured directly in `application.properties` (not via env vars): `max-size=30`, `min-size=5`, `acquisition-timeout=30`, `max-lifetime=PT30M`. JWT keys are loaded from `META-INF/resources/{publicKey,privateKey}.pem` — `quarkus.hibernate-orm.database.generation=none` means the MySQL schema must be pre-created.

## Architecture

### Request Flow (Chat Query)
```
Angular UI (4200)
  → POST /chat  to FastAPI App (8001)       # returns full JSON (non-streaming)
  → GET  /chat/stream  (SSE, token-by-token) # phases: thinking / tool / chunk
    → AriaAgent (LangGraph ReAct loop)
      → Static intent check (greetings, help → answered without LLM call)
      → preprocessor.analyze() — detects sensor type, period, query type
      → MCP Server (8000/sse) calls tools (DB queries, anomaly detection)
      → Output guard: quality score [0–1]; one automatic retry if score < 0.60
      → LLM backend (Groq / Gemini / Ollama / Cerebras / OpenRouter)
    → StreamingResponse back to Angular
```

### Daily Pipeline (03:00 UTC, APScheduler)
```
For each domain (energy, water, gaz, fuel):
  1. Extract last 96h from source DB
  2. Aggregate into daily_<domain> (hourly buckets, idempotent via ON DUPLICATE KEY UPDATE)
  3. Run HotStart anomaly detection
  4. Log results to pipeline_runs table
```

Five scheduled jobs total:
- **01:00 UTC** — historical data replay (loads past data into `daily_*` tables) + `archive_sync` (rebuilds monthly aggregates for Java dashboard)
- **03:00 UTC** — daily aggregation + HotStart anomaly detection
- **Every 2 hours** — proactive anomaly/prediction check → SSE broadcast to connected clients
- **04:00 UTC** — AI recommendation cycle: baselines, LLM-generated recommendations, ROI measurement (runs after AD pipeline at 03:00)
- **Sunday 02:00 UTC** — strategy audit: detects ColdStart devices with enough accumulated history (`_HOT_MIN_DAYS` distinct days in `daily_*`) to upgrade to HotStart, runs before the 03:00 AD pipeline

### Authentication Flow
```
Angular → POST /login (Java :8080) → JWT (RS256, 1h TTL)
Refresh token: 7 days
Issuer: https://ioit.bws.com
Keys: chatbot/backbws/src/main/resources/META-INF/resources/{public,private}Key.pem
```

## Key Files

### Python FastAPI
- `chatbot/bws_pfe/aria_api.py` — app entry point, lifespan management; registers all routers including `/transcribe` (voice) and `/vision` (image)
- `chatbot/bws_pfe/mcp_server/main.py` — MCP tool registration (17 tools: list_tables, describe_table, execute_query, realtime_data, thl_analysis, wm_analysis, energy_analysis, gm_analysis, fuel_analysis, alerts_summary, count_rows, search_in_table, database_summary, anomaly_detection, get_upcoming_predictions, ad_analysis, get_recommendations)
- `chatbot/bws_pfe/mcp_client/agent.py` — AriaAgent: ReAct loop, tool filtering by `allowed_modules`, `_TOOL_MODULE_MAP` dict, `_TOOL_LABELS` (UI labels shown during tool invocation), per-backend timeout and context-length limits; singleton instantiated in `aria_api.py` lifespan to survive hot-reload
- `chatbot/bws_pfe/mcp_client/llm_factory.py` — multi-backend LLM factory with `auto` routing; `KeyStateManager` handles per-backend API key rotation and exhausted-key persistence
- `chatbot/bws_pfe/mcp_client/intents.py` — static intent detection (greetings, help, identity); matched responses bypass the LLM entirely
- `chatbot/bws_pfe/mcp_client/output_guard.py` — quality gate: scores response [0–1], triggers one retry if score < `RETRY_THRESHOLD` (0.60)
- `chatbot/bws_pfe/mcp_client/preprocessor.py` — analyzes query intent: sensor type, period, query type, `is_data_query` flag
- `chatbot/bws_pfe/mcp_client/qr_parser.py` — extracts quick-reply suggestions from agent responses
- `chatbot/bws_pfe/mcp_client/prompt.py` — `ARIA_SYSTEM_PROMPT`: full system prompt with sensor vocabulary, tool routing rules, per-domain diagnostic chains (THL/WM/EN/GM/FUEL), domain thresholds, and FULL REPORT chain; dynamic context (device list) is cached for `ARIA_CONTEXT_TTL` seconds (default 300)
- `chatbot/bws_pfe/mcp_client/chart_builder.py` — converts raw MCP tool JSON output into Chart.js config lists; supports wm_analysis, energy_analysis, gm_analysis, fuel_analysis, thl_analysis, realtime_data, anomaly_detection; charts are sent alongside text responses
- `chatbot/bws_pfe/mcp_client/csv_export.py` — generates temporary CSV files (1h TTL, stored in system temp dir); exposed via `GET /download/{file_id}`; cleans up expired files on each new export
- `chatbot/bws_pfe/mcp_client/vision.py` — multimodal image analysis via Groq (`vision_router`, `/vision` endpoint)
- `chatbot/bws_pfe/mcp_client/transcribe.py` — voice transcription via AssemblyAI (`transcribe_router`, `/transcribe` endpoint)
- `chatbot/bws_pfe/mcp_client/history.py` — `MySQLHistoryManager`: auto-creates `chat_threads`/`chat_messages` on startup; falls back to in-memory list if MySQL unreachable
- `chatbot/bws_pfe/api/routes/` — 10 route modules: `chat` (POST /chat + GET /chat/stream SSE + GET /download/{file_id}), `threads` (conversation history), `feedback` (thumbs up/down), `reports` (daily summaries), `system` (health/status), `employees` (user module permissions), `analytics` (usage stats), `proactive` (push notifications), `sessions`, `recommendations`
- `chatbot/bws_pfe/api/pipeline/scheduler.py` — four APScheduler jobs (replay @01:00, daily pipeline @03:00, proactive check @/2h, recommendations @04:00)
- `chatbot/bws_pfe/api/pipeline/proactive.py` — proactive analysis logic: queries `ad_results` and `aria_predictions` for new anomalies/high predictions per active user; template-based messages (no LLM), 24h per-(user, domain) cooldown (1 notification/day max, survives dismissal)
- `chatbot/bws_pfe/api/pipeline/proactive_broadcaster.py` — in-memory SSE broadcaster; one `asyncio.Queue` per open SSE connection; `broadcast(user_id, payload)` fans out to all tabs for that user
- `chatbot/bws_pfe/api/models.py` — Pydantic request/response models; `AVAILABLE_MODULES` list defines the valid values for `allowed_modules`
- `chatbot/bws_pfe/mcp_server/device_resolver.py` — resolves `id_device` → `{nom, espace}` via JOIN on `device`/`espace` tables; 5-minute in-process cache; used by all domain tool modules
- `chatbot/bws_pfe/mcp_server/db/connection.py` — `QueuePool` (size=5, max_overflow=10); includes SQL safety validation to reject destructive statements
- `chatbot/bws_pfe/mcp_server/tools/` — 9 modules: `database.py` (list/describe/execute/count/search/summary), `sensors.py` (realtime_data + thl/wm/en/gm/fuel analysis), `alerts.py`, `anomaly.py`, `predictions.py`, `ad_analysis.py`, `reco_tool.py` (see below), `utils.py`; shared constants live in `_helpers.py` (`PERIOD_MAP`, `THRESHOLDS`, `SENSOR_TABLE_PRIORITY`)
- `chatbot/bws_pfe/eval/` — evaluation framework: `cases.py` (EvalCase definitions), `runner.py` (runs cases against live agent), `metrics.py`, `report.py`
- `chatbot/bws_pfe/api/pipeline/recommendation_engine.py` — LLM-powered recommendation pipeline: `compute_baselines()` (P10/P50/P90 per device/hour_of_week), signal detection, Chronos score enrichment, anti-fatigue suppression (dismissed ≥ 2× in 7d), cross-domain anomaly correlation, ROI measurement 48h post-acceptance; falls back to rule-based if LLM unavailable; writes to `aria_recommendations`
- `chatbot/bws_pfe/api/pipeline/reco/` — the engine's stages, one module each: `config` (DOMAIN_CONFIG, device labels), `baselines`, `signals`, `context` (anti-fatigue, device context, cross-domain), `llm` (prompt, call, validation, EN/AR translation), `fallback` (rule-based FR/EN/AR), `storage`, `roi`; `recommendation_engine.py` only orchestrates and re-exports the public API (`run_recommendation_cycle`, `generate_domain`, `compute_baselines`, `measure_roi`, `DOMAIN_CONFIG`)
- `chatbot/bws_pfe/mcp_server/tools/reco_tool.py` — MCP tool `get_recommendations`: reads `aria_recommendations` filtered by domain/status, returns ranked list with estimated savings in TND
- `chatbot/bws_pfe/api/routes/recommendations.py` — REST routes: `GET /recommendations` (filtered by role/domain/modules), `PATCH /recommendations/{id}` (status update), `POST /recommendations/refresh` (manual trigger), `GET /recommendations/summary`
- `chatbot/bws_pfe/rag/retriever.py` — MySQL FULLTEXT retrieval (with LIKE fallback) for building LLM context in `recommendation_engine.py`; reads `aria_knowledge_base` table; categories: `equipment_spec`, `maintenance_procedure`, `anomaly_playbook`, `intervention_report`, `contract_info`
- `chatbot/bws_pfe/api/pipeline/archive_sync.py` — syncs `archive_*_j` (daily) → `archive_*_m` (monthly) so the Java backend dashboard reads up-to-date monthly aggregates; run after each data replay or via `python -m api.pipeline.archive_sync`
- `chatbot/bws_pfe/api/pipeline/data_replay.py` — loads historical data into `archive_*` tables cycling over a date range (used to seed demo data)
- `chatbot/bws_pfe/api/pipeline/aggregator.py` — aggregates raw sensor readings from source tables into `daily_*` (hourly buckets) for each domain
- `chatbot/bws_pfe/api/pipeline/extractor.py` — pulls last N hours of raw data from source tables (`archive_en_p`, `archive_wm`, etc.) for the daily pipeline
- `chatbot/bws_pfe/api/pipeline/ad_runner.py` — bridges the daily pipeline to the `AD/` subprocess: triggers HotStart detection per domain and writes results to `ad_results`
- `chatbot/bws_pfe/api/pipeline/data_quality.py` — plausibility filter applied in `aggregate_energy`: a reading > `SPIKE_FACTOR` (20) × the median of its (device, phase) series is dropped (some LoRa meters occasionally report their cumulative index ~1e8 instead of the interval consumption ~1e5)
- `chatbot/bws_pfe/api/pipeline/clean_energy_spikes.py` — one-off cleanup of spikes already in `daily_energy` (`python -m api.pipeline.clean_energy_spikes` = dry-run, `--apply` backs up to `daily_energy_spikes_backup` then sets `cons_en = NULL`, `--restore` reverts)
- `chatbot/bws_pfe/api/pipeline/csv_importer.py` — flexible CSV → `daily_*` importer used by the `/system/import-csv` route; resolves column aliases (`_COL_ALIASES`), normalises wide→long energy format (L1/L2/L3 columns), and delegates aggregation to the same pipeline functions as the daily job

> `chatbot/bws_pfe/mcp_client/aria_agent.py` is **deprecated** — it re-exports `AriaAgent` from `agent.py` only for backward compatibility.

### Java Quarkus
- `chatbot/backbws/src/main/resources/application.properties` — DB, JWT, CORS config
- `chatbot/backbws/src/main/resources/seed_data.sql` — initial data; run manually after schema creation
- `chatbot/data_seed.sql` — broader seed SQL at repo root (device/espace/archive data); run once on fresh DB
- `chatbot/backbws/src/main/java/org/example/resource/` — 14 REST resources: Auth, Device, KPI, Electricity, Water, Gaz, Fuel, Alerts, AlertSseBroadcaster (SSE push), Chat, Recovery, Role, User
- `chatbot/backbws/src/main/java/org/example/service/` — 15 service classes (mostly one per resource domain, plus `JwtService`, `TwilioService`, `WaterArchiveJob`)
- `chatbot/backbws/src/main/java/org/example/dto/` — request/response DTOs; `entity/` — JPA entities; `util/` — JWT helpers
- Twilio SDK is included for SMS alert notifications (see Alerts service)

### Angular
- `chatbot/ioitfr/src/app/services/` — 22+ service files (aria, auth, analytics, domain-specific)
- `chatbot/ioitfr/src/app/shared/domain-dashboard.base.ts` — abstract base of the 4 domain dashboards (`electricity`, `gaz`, `water`, `fuel`): lifecycle, period loading, i18n refresh, KPI panel (`KpiDef`), chart modal, Chart.js instance registry (`renderChart(key, …)` destroys the previous instance); subclasses only implement `fetchData`/`buildKpi`/`buildCharts`/`buildModalChart`/`insightPrompts`. Chart.js controllers are registered once in `shared/chart-setup.ts`
- `chatbot/ioitfr/src/app/chatbot/` — chat UI with streaming, markdown, quick replies
- `chatbot/ioitfr/src/app/core/guards/` — `auth.guard.ts`, `role.guard.ts`
- `chatbot/ioitfr/src/app/core/interceptors/auth.interceptor.ts` — attaches JWT to every request
- `chatbot/ioitfr/src/assets/i18n/` — translation files (fr, ar, en)

### Anomaly Detection
- `AD/main.py` — unified CLI entry point; delegates to `runner.py` which auto-routes each device to HotStart or ColdStart based on row count vs `COLD_THRESHOLD_HOURS` (720 rows = 30 days)
- `AD/runner.py` — routing logic; spawns HotStart and ColdStart as isolated subprocesses to avoid PyTorch/sklearn import conflicts
- `AD/HotStart/main.py` — Chronos fine-tuning + residual-based detection
- `AD/HotStart/common/monthly_retrainer.py` — monthly Chronos fine-tuning job; runs independently from the daily detection pipeline
- `AD/ColdStart/main.py` — Z-score / IQR / Isolation Forest / Ensemble for new devices
- `AD/<domain>/config.yaml` — per-domain algorithm and device config

## Database Schema (key tables)

### Raw sensor source tables (read by extractor / pipeline)
- `archive_thl / archive_thl_h / rt_thl` — temperature/humidity/luminosity (priority order: archive > archive_h > rt)
- `archive_wm / archive_wm_h / rt_wm` — water meter
- `archive_en_p / archive_en_p_h / rt_en_p` — electrical energy (L1/L2/L3 phases)
- `archive_gm / archive_gm_h / rt_gm` — gas meter
- Priority order defined by `SENSOR_TABLE_PRIORITY` in `mcp_server/tools/_helpers.py`

### Aggregate & derived tables
- `aria_devices` — device registry (device_id, location, device_type)
- `daily_energy / daily_water / daily_gaz / daily_fuel` — hourly aggregates (device_id, phase for energy, date, hour, consumption); unique constraint on (device_id, [phase,] date, hour)
- `aria_anomalies` — legacy anomaly table (Java backend); distinct from `ad_results`
- `ad_results` — AD pipeline output: per-run anomaly scores with q10/q90 bounds (auto-created by `api/db.py`)
- `aria_predictions` — Chronos forecasts per device/domain/horizon (auto-created); unique on (run_at, domain, item_id, forecast_ts)
- `device_baselines` — P10/P50/P90 per (device_id, domain, hour_of_week) used by recommendation engine (auto-created)
- `aria_recommendations` — AI-generated recommendations with priority, estimated savings (TND), ROI feedback loop (auto-created)
- `aria_alerts` — active alerts with severity and status
- `aria_reports` — daily summary reports
- `aria_employees` — per-user `allowed_modules` (controls which domains agent sees)
- `chat_feedback` — thumbs up/down + comments per message; unique on (message_id, user_id)
- `pipeline_runs` — scheduler execution history with JSON summary

## Critical Constraints

- **MCP tool filtering**: `AriaAgent` filters available MCP tools based on the user's `allowed_modules` field via `_TOOL_MODULE_MAP` in `agent.py`. Adding a new tool requires an entry there. Tools mapped to `None` are always available; others require the matching module.

  | Tool | Required module |
  |---|---|
  | `wm_analysis` | `eau` |
  | `energy_analysis` | `énergie électrique` |
  | `gm_analysis` | `gaz` |
  | `fuel_analysis` | `carburant` |
  | `thl_analysis` | `équipements/capteurs` |
  | `alerts_summary` | `alertes` |
  | `realtime_data`, `anomaly_detection`, `get_upcoming_predictions`, `ad_analysis`, `get_recommendations`, `database_summary`, `list_tables`, `describe_table`, `count_rows`, `execute_query`, `search_in_table` | *(always available)* |

  Note: `dashboard` and `rapports` exist in `AVAILABLE_MODULES` but map to no MCP tools — they gate UI access only (Angular route guards), not agent behavior.

- **`_MODULE_TO_REALTIME`**: controls which sensor types `realtime_data` can query per module (e.g., `équipements/capteurs` → `['thl', 'sm', 'pir', 'ls']`; `eau` → `['wm']`; `énergie électrique` → `['en']`).

- **LLM backend timeouts & context limits** (from `agent.py`):

  | Backend | Timeout | Max history chars | Max history msgs |
  |---|---|---|---|
  | Ollama | 180 s | 1200 | 15 |
  | OpenRouter | 150 s | 1000 | 12 |
  | HuggingFace | 120 s | 800 | 8 |
  | Groq | 120 s | 600 | 8 |
  | Gemini | 120 s | 1000 | 12 |
  | Cerebras | 120 s | 800 | 10 |
  | *(default)* | 120 s | 800 | 10 |

- **Output quality scoring** (`output_guard.py`): four dimensions scored before sending to client.
  - `tools_called_ok` (45%) — MCP tools were actually invoked for data queries
  - `length_ok` (25%) — data responses ≥ 15 words; simple responses ≤ 120 words
  - `is_clean` (20%) — no hallucination signals (`[value]`, `placeholder`, `{{}}`, etc.)
  - `has_units` (10%) — technical responses include expected units (kWh, m³, °C, etc.)

  Note: the 🔴/🟠/🟡/🟢 badge is enforced by the **system prompt**, not by this gate.

  `RETRY_THRESHOLD = 0.60` — score below this triggers one retry. If `tools_called_ok=False` OR `is_clean=False`, the score is additionally capped at 0.55 to guarantee a retry. Do not add a second retry loop.

- **ReAct recursion limit**: `_REACT_RECURSION_LIMIT = 16` steps (1 tool call = 2 steps: AI + Tool), allowing up to 7 tool calls per turn. The FULL REPORT chain uses up to 9 tools — it stays within limit because some are batched in a single LLM step. Raising this value risks infinite loops.

- **Recommendation plausibility gate**: `recommendation_engine._flag_implausible_savings()` drops any `estimated_saving_tnd` above `_MAX_PLAUSIBLE_SAVING_TND` (50 000 TND/month per device — a symptom of a mis-declared meter unit, e.g. Wh or L reported as kWh or m³). The recommendation is kept with its relative deviation, but no amount or volume is written (LLM prompt + fallback texts), and the final value is forced to NULL even if the LLM computes one.
- **Few-shot IDs are fictitious**: the examples in `prompt.py` use `EXEMPLE-*` identifiers on purpose; `output_guard.py` treats `exemple-` in an answer as a hallucination (copied example). Never put real device IDs or realistic values in the few-shot block.
- **Energy phases**: energy domain has L1/L2/L3 phase granularity; all other domains are single-value per hour.
- **Idempotent pipeline**: `INSERT ON DUPLICATE KEY UPDATE` — safe to re-run for a given date.
- **CORS**: Java backend is hardcoded to `http://localhost:4200` — change `application.properties` for production. FastAPI CORS is controlled by `CORS_ORIGINS` env var.
- **Multi-language**: All Angular UI strings must use `ngx-translate` keys in `assets/i18n/{fr,ar,en}.json`. The agent also auto-detects language (fr/ar/en) and responds natively.
- **Streaming**: Chat responses use `StreamingResponse` in FastAPI — do not buffer the full response.
- **Multi-key rotation**: `KeyStateManager` persists exhausted API keys to `.key_state.json` across restarts; add multiple keys per backend as `PREFIX_API_KEY_1`, `_2` … `_9` env vars.
- **Startup backfill**: on FastAPI startup, the scheduler checks if `daily_*` data is stale (threshold: 2 days). If so, it automatically triggers a 30-day backfill followed by an AD detection run — both chained in the same thread to ensure `daily_*` is populated before AD reads it.
- **AD subprocess isolation**: `AD/runner.py` runs HotStart and ColdStart as subprocesses — do not import both in the same process (PyTorch/sklearn conflict).
- **Java schema**: `quarkus.hibernate-orm.database.generation=none` — the MySQL schema must exist before startup; Quarkus will not create or migrate it.
- **FastAPI docs**: Swagger UI (`/docs`), ReDoc (`/redoc`), and OpenAPI schema (`/openapi.json`) are disabled when `ENV=prod`. They are available in `ENV=dev` (default).
- **Auto-created tables**: Several tables are created on startup without migrations — `chat_threads`/`chat_messages` by `MySQLHistoryManager._ensure_tables()`; `aria_reports`, `chat_feedback`, analytics tables by `api/db.py:ensure_tables()`. If MySQL is unreachable at startup, the history manager falls back to an in-memory list.
- **Session TTL**: In-memory session map (`api/session.py`) expires entries after 4h of inactivity. This is not persistent — restarts lose all sessions.
- **Dynamic context cache**: `prompt.py` caches the device list injected into `ARIA_SYSTEM_PROMPT` for `ARIA_CONTEXT_TTL` seconds (default 300). Override with `ARIA_CONTEXT_TTL` env var to force more frequent DB reads.
- **Device resolver cache**: `device_resolver.py` maintains a separate 5-minute in-process cache of `id_device → {nom, espace}` mappings. When adding a new device type or renaming espace, both this cache and the prompt context cache must expire before the agent sees the change.
- **SQL safety gate**: `mcp_server/db/connection.py` rejects any statement containing destructive keywords (DROP, DELETE, TRUNCATE, etc.) before execution — the `execute_query` tool is read-only by design.
- **Rate limiting**: `api/helpers.py:rate_ok()` enforces 30 requests/min per IP. Exceeding this returns HTTP 429. The limit applies to all FastAPI routes.
- **Config validation**: Running `python mcp_server/config.py` (or `python mcp_client/config.py`) prints the full resolved config and raises `ValueError` if required vars are missing (e.g. `DB_PASSWORD`). Useful for debugging `.env` issues.
- **All LLM API keys follow the `PREFIX_API_KEY_1`…`_9` rotation pattern** — Groq, Gemini, Cerebras, OpenRouter, HuggingFace, and Vision all support multiple keys; `KeyStateManager` handles rotation uniformly.
