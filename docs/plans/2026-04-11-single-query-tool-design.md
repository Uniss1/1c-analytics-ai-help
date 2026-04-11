# Single Query Tool: надёжный tool calling через 1 инструмент

**Дата:** 2026-04-11
**Статус:** утверждён

## Проблема

Gemma 4 E2B (5B) с 7 инструментами ненадёжно выбирает tool и заполняет параметры. При единственном регистре модель всё равно возвращает текст вместо tool call или выбирает неверный инструмент.

## Решение

Один инструмент `query` с параметром `mode: aggregate | group_by | compare`. Модель всегда вызывает одну функцию — не выбирает между инструментами. Шаблонное форматирование ответа без LLM.

## 3 mode

| Mode | Когда | Пример вопроса | Формат ответа |
|------|-------|----------------|---------------|
| `aggregate` | Одно число с фильтрами | "Какая выручка за март 2025?" | "Выручка по Консолидация по факту за март 2025 составляет: 150 млн руб." |
| `group_by` | Разбивка по измерению | "Выручка по всем ДЗО за март" | Список: ДЗО1: 150 млн, ДЗО2: 80 млн... |
| `compare` | Два сценария рядом | "Факт vs бюджет по выручке за март" | Факт: 150 млн, Бюджет: 200 млн, Отклонение: −50 млн (−25%) |

## Схема инструмента

Генерируется динамически из metadata (enum-ы из allowed_values):

```json
{
  "type": "function",
  "function": {
    "name": "query",
    "description": "Query 1C analytics register. ALWAYS call this tool.",
    "parameters": {
      "type": "object",
      "properties": {
        "mode": {
          "type": "string",
          "enum": ["aggregate", "group_by", "compare"],
          "description": "Query type: aggregate = single value, group_by = breakdown by dimension, compare = two scenarios side by side"
        },
        "resource": {
          "type": "string",
          "enum": ["Сумма"],
          "description": "Which resource to aggregate"
        },
        "metric": {
          "type": "string",
          "enum": ["from metadata"],
          "description": "Business metric (Показатель). Default: Выручка"
        },
        "scenario": {
          "type": "string",
          "enum": ["from metadata"],
          "description": "Scenario filter. For compare mode — omit this, use compare_values instead"
        },
        "company": {
          "type": "string",
          "enum": ["from metadata"],
          "description": "Company (ДЗО). Default: Консолидация"
        },
        "contour": {
          "type": "string",
          "enum": ["from metadata"],
          "description": "Contour. Default: свод"
        },
        "year": {
          "type": "integer",
          "description": "Year (e.g. 2025)"
        },
        "month": {
          "type": "integer",
          "description": "Month 1-12. 'март' = 3, 'январь' = 1"
        },
        "group_by": {
          "type": "string",
          "enum": ["company", "scenario", "metric"],
          "description": "Only for group_by mode. Dimension to break down by"
        },
        "compare_values": {
          "type": "array",
          "items": {"type": "string"},
          "description": "Only for compare mode. Exactly 2 values, e.g. ['Факт', 'Бюджет']"
        },
        "compare_by": {
          "type": "string",
          "enum": ["scenario", "company"],
          "description": "Only for compare mode. Dimension to compare across. Default: scenario"
        }
      },
      "required": ["mode", "resource", "year", "month"]
    }
  }
}
```

## System prompt

Генерируется из metadata. Содержит:
1. Описание регистра
2. Перечисление доступных enum-значений (двойное подкрепление — и в prompt, и в schema)
3. Явные дефолты (scenario→Факт, company→Консолидация, contour→свод)
4. Краткое описание каждого mode с примерами-триггерами
5. 5 few-shot примеров (2 aggregate, 1 group_by, 1 compare, 1 с нестандартным metric)
6. 5 коротких правил

```
You are an analytics assistant for 1C register "{register_name}".
{register_description}

You have ONE tool: "query". ALWAYS call it. NEVER reply with text.

Available metrics: Выручка, Маржа, EBITDA, ...
Available scenarios: Факт, План, Бюджет
Available companies: Консолидация, ДЗО1, ДЗО2, ...
Default company: Консолидация
Default contour: свод

## How to pick mode:

aggregate — one number for specific filters
  "какая выручка за март 2025?" → aggregate
  "EBITDA по ДЗО1 за январь?" → aggregate

group_by — breakdown by a dimension
  "выручка по всем ДЗО за март" → group_by, group_by=company
  "выручка по сценариям за март" → group_by, group_by=scenario

compare — two values of same dimension side by side
  "факт vs бюджет по выручке за март" → compare, compare_by=scenario, compare_values=["Факт", "Бюджет"]
  "сравни план и факт EBITDA за январь" → compare, compare_by=scenario, compare_values=["Факт", "План"]

## Examples:

User: Какая выручка за март 2025?
→ query(mode="aggregate", resource="Сумма", metric="Выручка", scenario="Факт", year=2025, month=3)

User: Выручка по ДЗО1 по бюджету за март 2025
→ query(mode="aggregate", resource="Сумма", metric="Выручка", company="ДЗО1", scenario="Бюджет", year=2025, month=3)

User: Выручка по всем ДЗО за март 2025
→ query(mode="group_by", resource="Сумма", metric="Выручка", group_by="company", year=2025, month=3)

User: Сравни факт и бюджет по выручке за март 2025
→ query(mode="compare", resource="Сумма", metric="Выручка", compare_by="scenario", compare_values=["Факт", "Бюджет"], year=2025, month=3)

User: EBITDA по бюджету за январь 2025
→ query(mode="aggregate", resource="Сумма", metric="EBITDA", scenario="Бюджет", year=2025, month=1)

## Rules:
1. ALWAYS call the query tool. NEVER respond with text.
2. Use ONLY values from the enums above.
3. If scenario not mentioned, default to "Факт".
4. If company not mentioned, default to "Консолидация".
5. Extract month from Russian: март=3, январь=1, апрель=4, etc.
```

## Flow

```
User question
    │
    ▼
Router LLM: "data" or "knowledge"
    │
    ▼ (data)
find_register() — один регистр, fallback работает
    │
    ▼
Gemma: query(mode, params) — 1 инструмент, всегда tool call
    │
    ▼
_normalize_params() — Latin→Cyrillic, подставить дефолты
    │
    ▼
validate() — проверить enums, year/month, mode-specific params
    │
    ▼
execute_tool() → POST /analytics/execute → 1C
    │
    ▼
format_answer() — шаблонный, БЕЗ LLM
```

**Ключевое:** убираем LLM из форматирования. Было 3 LLM-вызова (router + Gemma + formatter), станет 2.

## Шаблонное форматирование (answer_formatter.py)

### aggregate
```
"{metric} по {company} по {scenario} за {month_name} {year} составляет: {value} руб."
```

### group_by
```
"{metric} по {group_by_name} за {month_name} {year} ({scenario}):
- {dim_value_1}: {value_1} руб.
- {dim_value_2}: {value_2} руб.
..."
```

### compare
```
"{metric} за {month_name} {year}:
- {value_1_name}: {value_1} руб.
- {value_2_name}: {value_2} руб.
- Отклонение: {diff} руб. ({percent}%)"
```

### Форматирование чисел
```python
def _fmt_number(value: float) -> str:
    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:,.1f} млрд"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:,.1f} млн"
    if abs(value) >= 1_000:
        return f"{value / 1_000:,.1f} тыс."
    return f"{value:,.0f}"
```

## Изменения в коде

### Меняется

| Файл | Что |
|------|-----|
| `api/tool_defs.py` | `build_tools()` → 1 инструмент `query`. `build_system_message()` → few-shot prompt. Убираем вспомогательные функции для 7 tools |
| `api/tool_caller.py` | `VALID_TOOLS = {"query"}`. `_normalize_params()` — mode-aware маппинг. Разворачивает mode обратно в tool name для 1C |
| `api/param_validator.py` | Валидация по mode: aggregate — не нужны group_by/compare_values; compare — нужны compare_by + compare_values(2); group_by — нужен group_by |
| `api/main.py` | `_handle_data()` → `format_answer()` вместо `format_response()` (LLM) |
| `scripts/calibrate_tools.py` | Кейсы под 1 инструмент, проверка параметров |

### Добавляется

| Файл | Что |
|------|-----|
| `api/answer_formatter.py` | `format_answer(mode, params, data, computed)` → строка. Три шаблона + `_fmt_number()` |

### Удаляется

| Файл | Почему |
|------|--------|
| `api/formatter.py` | LLM-форматирование не нужно для data-запросов |

### Не меняется

`api/metadata.py`, `api/router.py`, `api/config.py`, `api/onec_client.py`, `scripts/sync_metadata.py`

## Обработка ошибок

### Gemma не вернула tool call
Retry как сейчас (MAX_RETRIES=2). С 1 инструментом случается значительно реже.

### Пользователь не указал период
Python переспрашивает: "Уточните период: за какой год и месяц?"

### Значение не из enum
1. Gemma — enum в схеме ограничивает выбор
2. param_validator — ловит и показывает allowed_values

### Несовместимые параметры
- `mode=aggregate` + `group_by` → игнорируем group_by
- `mode=compare` без `compare_values` → переспрашиваем
- `mode=group_by` без `group_by` → переспрашиваем

### 1С ошибки
Без изменений: `no_data` → "Данные не найдены", `invalid_params` → показать allowed_values.

## Калибровочные кейсы

```python
CASES = [
    # aggregate — базовый
    ("Какая выручка за март 2025?",
     {"mode": "aggregate", "metric": "Выручка", "year": 2025, "month": 3}),

    # aggregate — с конкретным ДЗО и сценарием
    ("Выручка по ДЗО1 по бюджету за март 2025",
     {"mode": "aggregate", "metric": "Выручка", "company": "ДЗО1", "scenario": "Бюджет", "year": 2025, "month": 3}),

    # aggregate — другой metric
    ("EBITDA по бюджету за январь 2025",
     {"mode": "aggregate", "metric": "EBITDA", "scenario": "Бюджет", "year": 2025, "month": 1}),

    # group_by — по ДЗО
    ("Выручка по всем ДЗО за март 2025",
     {"mode": "group_by", "metric": "Выручка", "group_by": "company", "year": 2025, "month": 3}),

    # group_by — по сценариям
    ("Выручка по сценариям за март 2025",
     {"mode": "group_by", "metric": "Выручка", "group_by": "scenario", "year": 2025, "month": 3}),

    # compare — факт vs бюджет
    ("Сравни факт и бюджет по выручке за март 2025",
     {"mode": "compare", "metric": "Выручка", "compare_by": "scenario",
      "compare_values": ["Факт", "Бюджет"], "year": 2025, "month": 3}),

    # compare — факт vs план
    ("Факт vs план EBITDA за январь 2025",
     {"mode": "compare", "metric": "EBITDA", "compare_by": "scenario",
      "compare_values": ["Факт", "План"], "year": 2025, "month": 1}),

    # edge: нет периода → needs_clarification
    ("Какая выручка?",
     {"mode": "aggregate", "metric": "Выручка", "needs_clarification": True}),

    # edge: разговорная форма
    ("Сколько заработали в марте 2025?",
     {"mode": "aggregate", "metric": "Выручка", "year": 2025, "month": 3}),

    # edge: маржа по ДЗО
    ("Маржа по всем ДЗО за февраль 2025",
     {"mode": "group_by", "metric": "Маржа", "group_by": "company", "year": 2025, "month": 2}),
]
```

## Ожидаемые улучшения

| Метрика | Было (7 tools) | Станет (1 tool) |
|---------|----------------|-----------------|
| Tool call rate | ~85-95% | ~99% (1 инструмент + tool_choice) |
| Правильный mode | ~80% | ~95% (3 значения enum vs 7 tool names) |
| Правильные params | ~75% | ~90% (few-shot + enum constraints) |
| Latency | 3 LLM calls | 2 LLM calls |
| Формат ответа | Непредсказуемый | Единообразный |
