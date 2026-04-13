# 1C Analytics AI Help

**AI-помощник для 1С Аналитики — отвечает на вопросы по данным и методологии на естественном языке.**

Пользователь задаёт вопрос в чате (виджет внутри дашборда или standalone web-чат), система определяет тип вопроса, вызывает единый `query`-инструмент через SLM (Gemma 4 E2B / qwen3.5:4b) по Ollama `/api/chat`, отправляет JSON-параметры в 1С HTTP-сервис и возвращает отформатированный ответ по шаблону (без LLM).

## Возможности

- **Один `query`-tool с `mode`-enum** — модель выбирает режим через tool calling:
  - `aggregate` — одно число за период ("Какая выручка за март?")
  - `group_by` — разбивка по измерению, в т.ч. top-N ("Выручка по ДЗО")
  - `compare` — сравнение двух значений одного измерения ("Факт vs план за март")

  На стороне 1С эти три режима маппятся в 7 типов запросов (aggregate, group_by,
  top_n, time_series, compare, ratio, filtered). Python передаёт только JSON.
- **Self-healing loop** — при провале валидации параметров текст ошибки
  возвращается модели, и она перевызывает tool до 3 раз перед тем как спросить
  пользователя. Детали: [`docs/decisions/2026-04-12-self-healing.md`](docs/decisions/2026-04-12-self-healing.md).
- **Вопросы по методологии** — поиск в базе знаний (Wiki.js + RAG)
- **Контекст дашборда** — виджет автоматически передаёт контекст текущего дашборда
- **Debug-панель** — в web UI видно какой инструмент вызвала модель, параметры, результат
- **Безопасность** — текст запроса 1С нигде не передаётся по сети, только JSON-параметры

## Быстрый старт

```bash
git clone https://github.com/Uniss1/1c-analytics-ai-help.git
cd 1c-analytics-ai-help
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Отредактировать .env — указать адреса Ollama, 1С, ai-chat

python3 scripts/seed_metadata.py
uvicorn api.main:app --reload --port 8000
curl http://localhost:8000/health
# → {"status": "ok"}
```

Web-чат: `http://localhost:8000/web/`

## Тесты

```bash
pytest tests/ -v
```

Калибровка tool calling (требует Ollama с моделью, поддерживающей tool calling):

```bash
python3 scripts/calibrate_tools.py --model qwen3.5:4b --url http://<host>:11434
# 18 кейсов: 12 базовых + 6 degraded (проверка self-healing loop)
```

## Архитектура

```
Пользователь → виджет / web-чат
                    ↓
              nginx (rate limit)
                    ↓
              FastAPI (:8000)
                    ↓
            ┌── Router (LLM) ──┐
            ↓                  ↓
         "data"           "knowledge"
            ↓                  ↓
      metadata.py         wiki_client.py
      find_register()     → ai-chat сервис
            ↓
      tool_caller.py
      Ollama /api/chat + single query tool
            ↓
      param_validator.py ←─┐
      быстрая проверка JSON │ self-healing loop
            ↓               │ (до 3 ретраев с feedback)
      (ok) ─────────────────┘
            ↓
      onec_client.py → 1С HTTP-сервис
      POST /analytics/execute (JSON)
            ↓
      answer_formatter.py (шаблон, без LLM) → ответ
```

1С HTTP-сервис принимает JSON с инструментом и параметрами, сам собирает и выполняет запрос на языке 1С. Спецификация эндпоинта: [`docs/1c-http-service-spec.md`](docs/1c-http-service-spec.md).

## Требования

| Компонент | Версия |
|-----------|--------|
| Python | 3.11+ |
| Ollama | 0.6+ |
| Gemma 4 E2B | 5.1B Q4_K_M (tool calling) |
| SQLite | 3.x (встроен в Python) |
| 1С Аналитика | с HTTP-сервисом `/analytics/execute` |
| ai-chat | Uniss1/ai-chat на порту 3001 |

## Стек

| Слой | Технологии |
|------|-----------|
| API | FastAPI, uvicorn, Pydantic Settings |
| Tool calling | SLM (Gemma 4 E2B / qwen3.5:4b) через Ollama `/api/chat` |
| Данные | SQLite (metadata + history), 1С HTTP-сервис |
| Знания | ai-chat (Wiki.js + pgvector + RAG) |
| Фронтенд | Vanilla JS виджет + standalone web-чат |
| Прокси | nginx (reverse proxy, script injection) |

## Структура проекта

```
api/
├── main.py             # FastAPI entrypoint, chat flow + self-healing loop
├── config.py           # Pydantic Settings (.env)
├── tool_defs.py        # Single query tool (JSON Schema, Latin keys)
├── tool_caller.py      # Ollama /api/chat + retry с validation feedback
├── param_validator.py  # Валидация JSON-параметров до отправки в 1С
├── onec_client.py      # HTTP-клиент 1С (execute_tool + execute_query)
├── metadata.py         # Поиск регистра по ключевым словам
├── router.py           # Классификация intent (data / knowledge)
├── answer_formatter.py # Шаблонное форматирование ответа (без LLM)
├── llm_client.py       # Клиент Ollama (multi-GPU)
├── wiki_client.py      # Клиент ai-chat (база знаний)
├── history.py          # История чата SQLite
├── date_parser.py      # Парсинг периодов из русского текста
├── query_templates.py  # legacy
└── query_generator.py  # legacy
scripts/
├── calibrate_tools.py  # Калибровка tool calling (12 базовых + 6 degraded)
├── seed_metadata.py    # Заполнение metadata.db из registers.yaml
└── sync_metadata.py    # Синхронизация из 1С
tests/                  # pytest (unit + e2e, respx-мокинг)
web/                    # Standalone web-чат с debug-панелью
widget/                 # Виджет для встраивания в 1С Аналитику
docs/
├── 1c-http-service-spec.md   # Контракт /analytics/execute
├── 1c-http-service-module.md # BSL-код HTTP-сервиса
├── decisions/                # ADR (self-healing и т.п.)
├── specs/                    # Дизайн-доки
└── superpowers/              # Планы и воркфлоу
```
