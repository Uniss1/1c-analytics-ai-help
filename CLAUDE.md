# 1C Analytics AI Help

AI-assistant for 1C Analytics dashboards. Users ask questions in Russian, system selects a tool via Gemma 4 E2B, sends JSON params to 1C HTTP service, returns formatted answer.

## Critical Rules

- **All LLM prompts in English.** Only `formatter.py` instructs to answer in Russian.
- **No hardcoded register metadata.** Always load from `metadata.db` via `get_all_registers()`.
- **registers.yaml is gitignored.** Template: `registers.example.yaml`. Never commit real registers.
- **Tool caller uses Ollama native API** (`/api/chat`), NOT `/v1/chat/completions`. The OpenAI-compatible endpoint breaks tool calling for Gemma.
- **Dimension keys must be Latin** in tool schemas. Cyrillic in JSON Schema confuses small models. See `_dim_key()` mapping in `tool_defs.py`.
- **Exclude technical dimensions** from tool schemas: `Показатель_номер`, `Ед_изм`, `Масштаб`, `Месяц`, `ПризнакДоход`. These are auxiliary 1C Analytics fields, not user-queryable.
- **1C query text never crosses network.** Only JSON params. 1C builds queries internally.

## Commands

```bash
# Dev
uvicorn api.main:app --reload --port 8000

# Tests
pytest tests/ -v

# Metadata: seed from YAML
python3 scripts/seed_metadata.py

# Metadata: sync from 1C (discovers dimensions/resources)
python3 scripts/sync_metadata.py

# Calibrate tool calling (needs Ollama + gemma4:e2b)
python3 scripts/calibrate_tools.py -v
```

## Architecture

```
User → nginx → FastAPI(:8000)
                  ↓
           Router (LLM, GPU 0) → "data" | "knowledge"
                  ↓                         ↓
           metadata.py                 wiki_client.py
           find_register()             → ai-chat
                  ↓
           tool_caller.py
           Ollama /api/chat + tools
                  ↓
           param_validator.py
                  ↓
           onec_client.py → POST /analytics/execute (JSON)
                  ↓
           formatter.py (LLM) → answer in Russian
```

## Key Files

| Path | Purpose |
|------|---------|
| `api/tool_defs.py` | 7 tool schemas for Gemma (Latin keys, enum values in Russian) |
| `api/tool_caller.py` | Ollama `/api/chat` with tools, retry logic, response parsing |
| `api/param_validator.py` | Validate JSON params before sending to 1C |
| `api/metadata.py` | Register lookup by keywords. **Single-register fallback**: if only 1 register in DB, uses it without keyword match |
| `api/onec_client.py` | HTTP client to 1C `/analytics/execute` |
| `api/config.py` | Pydantic Settings from `.env`. Default model: `gemma4:e2b` |
| `registers.example.yaml` | Template for register metadata (gitignored `registers.yaml` is the real config) |
| `scripts/seed_metadata.py` | Drops and recreates all tables from `registers.yaml` |
| `docs/1c-http-service-spec.md` | Contract for 1C HTTP service endpoint |
| `docs/1c-http-service-module.md` | Full BSL code for 1C HTTP service module |

## 7 Tools (tool_defs.py)

| Tool | Use case | Key params |
|------|----------|------------|
| `aggregate` | Single sum for period | resource, filters, period |
| `group_by` | Breakdown by dimension | + group_by |
| `top_n` | Ranking (default limit=10) | + group_by, limit |
| `time_series` | Monthly dynamics | period optional |
| `compare` | Two values side by side | + compare_by, values (2) |
| `ratio` | Metric division | + numerator, denominator |
| `filtered` | HAVING threshold | + condition_operator, condition_value |

## Dimension Key Mapping (tool_defs.py)

Model sees Latin keys, 1C gets Cyrillic. Both directions via `_dim_key()` / `key_to_dim()`:

```
Сценарий ↔ scenario    КонтурПоказателя ↔ contour
Показатель ↔ metric    ДЗО ↔ company
Масштаб ↔ scale        Подразделение ↔ department
ПризнакДоход ↔ income_flag    Ед_изм ↔ unit
Месяц ↔ period_month   Показатель_номер ↔ metric_number
```

**When adding new registers:** add Latin mappings for ALL dimensions. Missing mappings = Cyrillic in schema = broken tool calling.

## Config (.env)

```bash
OLLAMA_BASE_URL=http://localhost:11434  # Ollama address
MODEL_NAME=gemma4:e2b                   # Tool calling model
ONEC_BASE_URL=http://1c-server/base/hs/ai
ONEC_USER=ai_assistant
ONEC_PASSWORD=
```

## 1C HTTP Service

Full BSL module code: `docs/1c-http-service-module.md`
Spec: `docs/1c-http-service-spec.md`
Platform XML specs: `docs/1c-platform-specs/` (from cc-1c-skills)

One module in Конфигуратор → HTTP-сервисы → `АИАналитика` → Module.bsl

## Known Issues / TODO

- **Metadata enrichment needed**: `sync_metadata.py` should use LLM interview to classify fields as technical vs user-facing. Currently technical fields are hardcoded in `tool_defs.py`.
- **Ollama port**: production server uses `10.10.90.188:11443`, not default 11434.

## Modular Docs

See `.claude/rules/` for domain-specific rules:
- `1c-module.md` — 1C BSL code patterns and common errors

@docs/1c-http-service-spec.md
@docs/superpowers/specs/2026-04-10-smart-1c-backend-design.md
