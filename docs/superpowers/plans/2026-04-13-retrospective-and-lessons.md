# Retrospective Lessons → CLAUDE.md + Obsidian raw — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Зафиксировать уроки 4 дней работы над 1C Analytics AI Help в двух местах: проектном `CLAUDE.md` (actionable правила) и raw-файле для Obsidian-vault'а `obsidian-llm-wiki` (исходник для curator INGEST).

**Architecture:** Чисто документационная задача. Никакого кода — только два markdown-файла. Артефакт 1 правит существующий `CLAUDE.md` (вставка блока), артефакт 2 создаёт новый файл в чужом git-репо vault'а (не коммитим из этого репо).

**Tech Stack:** Markdown, Obsidian-conventions (kebab-case filenames, `[[wikilinks]]`), git.

**Reference:** `docs/superpowers/specs/2026-04-13-retrospective-and-lessons-design.md`

---

## File Structure

| Файл | Действие | Назначение |
|------|---------|-----------|
| `CLAUDE.md` (корень репо) | Modify (insert) | Добавить блок `## Lessons learned` после `## Known Issues / TODO`, перед `## Modular Docs` |
| `/mnt/c/Users/Admin/Projects/obsidian-llm-wiki/raw/2026-04-13-1c-analytics-slm-tool-calling-retrospective.md` | Create | Сырой источник для INGEST в Obsidian-vault'е |
| `docs/superpowers/specs/2026-04-13-retrospective-and-lessons-design.md` | Already created | Spec (создан в брейнсторминге) |

**Граница ответственности:**
- Артефакт 1 = коммит в `Uniss1/1c-analytics-ai-help`
- Артефакт 2 = НЕ коммитим из этого репо (живёт в другом git-репо vault'а; пользователь сам решит, что с ним делать)

---

## Pre-flight checks

### Task 0: Проверка состояния перед началом

**Files:**
- Read: `CLAUDE.md`
- Read: `/mnt/c/Users/Admin/Projects/obsidian-llm-wiki/CLAUDE.md`

- [ ] **Step 1: Убедиться, что spec на месте**

Run: `ls docs/superpowers/specs/2026-04-13-retrospective-and-lessons-design.md`
Expected: файл существует.

- [ ] **Step 2: Зафиксировать текущий размер CLAUDE.md**

Run: `wc -l CLAUDE.md`
Expected: 131 строк (если другое — плохо, это значит файл изменился со времени брейнсторминга).

- [ ] **Step 3: Убедиться, что vault на месте и raw/ существует**

Run: `ls /mnt/c/Users/Admin/Projects/obsidian-llm-wiki/raw/ | head -5`
Expected: список файлов (минимум несколько `.md`). Если directory не существует — STOP, написать пользователю, не делать `mkdir`.

- [ ] **Step 4: Перечитать конвенции vault'а**

Прочитать `/mnt/c/Users/Admin/Projects/obsidian-llm-wiki/CLAUDE.md` целиком. Запомнить:
- Имена файлов: kebab-case, English
- Тело: русский, технические термины на English
- raw/ файлы — без frontmatter (это сырьё для INGEST, не финальные wiki-страницы)
- Шаблон wiki-страницы НЕ применяется к raw/ — в raw свободная форма

- [ ] **Step 5: Проверить git status**

Run: `git status`
Expected: чистый рабочий каталог либо только untracked plans. Если modified files есть — STOP, спросить пользователя.

---

## Артефакт 1 — блок Lessons в CLAUDE.md

### Task 1: Вставить блок «Lessons learned» в CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` (вставка после строки 123, перед `## Modular Docs`)

**Контекст вставки:** блок идёт сразу после «Known Issues / TODO». Перед строкой `## Modular Docs`.

- [ ] **Step 1: Сделать Edit**

Точная вставка через Edit-tool. `old_string` находит существующую границу, `new_string` добавляет новый блок ПЕРЕД ней, не трогая её содержимое.

```
old_string:
## Modular Docs

new_string:
## Lessons learned

Уроки 4 дней постройки. Каждое правило — императив + 1 строка «почему».

**SLM tool calling (5B-класс моделей):**
- Один tool с `mode` enum > 7 разных tools — модель путается в выборе имени функции
- Латинские ключи в JSON Schema > кириллические — кириллица в schema ломает small models
- Enum-значения и дефолты дублируем и в schema, и в system message — двойное подкрепление
- Перед бенчмарком: `cat .env | grep MODEL_NAME` — не доверять докам, .env может расходиться
- Ollama native `/api/chat`, не OpenAI-compat `/v1/chat/completions` — для Gemma тулы ломаются

**Архитектурные:**
- Текст 1С-запроса не пересекает сеть. Только JSON params (безопасность + корректность синтаксиса бесплатно)
- Правило, живущее в двух местах → выноси helper. Technical-dim фикс ловили дважды
- Не ставить LLM туда, где работает шаблон. Каждый LLM-вызов = +1–3 сек латентности
- Чинить root cause, не симптом: `invalid_params` на корректный resource = баг валидатора, не клиента

**1С платформа (часто граблями):**
- URL-шаблоны HTTP-сервиса односегментные: `/analytics_execute`, не `/analytics/execute`
- РегистрСведений имеет три коллекции: `Измерения`, `Ресурсы`, `Реквизиты` — проверять обе при поиске поля
- Оператор сравнения подставлять через switch/case, не конкатенацией строки (защита от инъекций)

**Process для этой кодобазы:**
- После любого фикса в data flow — рестарт `uvicorn` + реальный вопрос в вебе. CI-зелёный ≠ работает в браузере
- Коррекция от пользователя → обновить ВСЕ источники истины сразу: код + spec + README + memory entry. Иначе та же ошибка вернётся
- Untracked `.md` план без коммита = долг. Либо коммитим, либо удаляем

## Modular Docs
```

- [ ] **Step 2: Проверить размер файла**

Run: `wc -l CLAUDE.md`
Expected: 161 строка (131 + 30 новых строк ± 2). Если > 200 — STOP, ужать список.

- [ ] **Step 3: Визуальная проверка вставки**

Run: `sed -n '120,165p' CLAUDE.md`
Expected: видно блок «## Lessons learned» сразу после «## Known Issues / TODO», и `## Modular Docs` идёт следом без потери содержимого.

- [ ] **Step 4: Lint-check на дубликаты с уже существующими правилами**

Run: `grep -ni 'технических\|technical\|роутер\|router\|шаблон URL' CLAUDE.md`
Expected: нет правил, сформулированных дважды (если вижу дубль — оставить только в Lessons и убрать из старого места ИЛИ если дубль уместен — пометить «см. ## Lessons learned»). Скорее всего дублей не будет — старые секции в CLAUDE.md описывают «как устроено», Lessons — «что не повторять».

- [ ] **Step 5: Коммит CLAUDE.md и spec одним коммитом**

```bash
git add CLAUDE.md docs/superpowers/specs/2026-04-13-retrospective-and-lessons-design.md
git status   # подтвердить — staged ровно эти два файла, ничего лишнего
git commit -m "$(cat <<'EOF'
docs: add Lessons learned section to CLAUDE.md

Извлечённые из 4 дней работы (Apr 10-13) повторяющиеся уроки:
SLM tool calling, архитектурные паттерны, 1C-платформенные грабли
и process anti-patterns.

Source: docs/superpowers/specs/2026-04-13-retrospective-and-lessons-design.md
Парный артефакт (raw для obsidian-llm-wiki) живёт в другом git-репо.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: один commit, файл CLAUDE.md ≤ 200 строк, spec тоже в коммите.

- [ ] **Step 6: Подтвердить чистый статус**

Run: `git status`
Expected: working tree clean (или untracked files, не имеющие отношения к этому коммиту).

---

## Артефакт 2 — raw-файл для Obsidian vault'а

### Task 2: Создать raw-файл с ретроспективой

**Files:**
- Create: `/mnt/c/Users/Admin/Projects/obsidian-llm-wiki/raw/2026-04-13-1c-analytics-slm-tool-calling-retrospective.md`

**Note про коммит:** этот файл лежит в другом git-репо (vault'а). Из ЭТОГО проекта мы его НЕ коммитим. После создания — сообщить пользователю; он сам решит коммитить ли в vault.

- [ ] **Step 1: Создать файл через Write**

Полное содержимое (под INGEST curator'а):

```markdown
# 1C Analytics AI Help — ретроспектива (4 дня, 2026-04-10…04-13)

> Источник: проект `/home/dmin/projects/1c-analytics-ai-help`.
> Стек: SLM tool calling (qwen3.5:4b / gemma4:e2b) через Ollama,
> FastAPI backend, 1С HTTP-сервис на BSL.

## Контекст проекта

AI-помощник для дашбордов 1С Аналитики. Пользователь задаёт вопросы
по-русски, система выбирает tool через малую LLM (qwen3.5:4b или
gemma4:e2b), отправляет JSON-параметры в 1С HTTP-сервис, форматирует
ответ шаблонно (без LLM в форматтере).

Цифры:
- 4 дня работы (2026-04-10…04-13)
- 30+ коммитов в main
- 6 крупных архитектурных переделок
- Финальный cleanup-коммит: −1736 / +149 строк
- 71/71 тестов зелёные на конец

## SLM tool calling — что работает

### Single tool с `mode` enum

Один tool `query` с параметром `mode: aggregate | group_by | compare`
надёжнее семи отдельных tools. Малая модель (5B) не путается в выборе
имени функции, всегда вызывает одну.

### Латинские ключи в JSON Schema

`scenario`, `metric`, `company` вместо `Сценарий`, `Показатель`, `ДЗО`.
Кириллица в JSON Schema ломает токенизацию small models. Маппинг
Latin↔Cyrillic делается на стороне Python после tool call.

### Enum в schema И в system message

Двойное подкрепление: и JSON Schema constraint, и явное перечисление
в system prompt. Только schema — модель иногда промахивается.
Только prompt — нет hard constraint.

### tool_choice="required" + Ollama native API

`/api/chat` вместо OpenAI-compatible `/v1/chat/completions`. Для Gemma
4 E2B `/v1` отдаёт сломанный tool calling, native API работает.

### Self-healing validation loop

После tool call валидируем параметры; если invalid — отдаём ошибки
обратно в model как user message и просим скорректировать. Дешёвый
паттерн (1 дополнительный round-trip), вытянул baseline 91.7% → 99%.

### Metadata-driven dynamic schema

Tool schema собирается из `metadata.db` per-register. Enum-значения
для `metric`, `company` и т.д. подставляются из реальных значений
конкретного регистра. Sync — через interactive interview в
`sync_metadata.py`.

### Шаблонный formatter

Ответ собирается из шаблонов («Выручка по {company} за {month} {year}
составляет {value} руб.»), не через LLM. Детерминированный вывод,
0мс латентности, нечего тестировать на flakiness.

## SLM tool calling — что НЕ работает

### 7 различных tool names для 5B модели

Изначально было 7 tools (`aggregate`, `group_by`, `top_n`,
`time_series`, `compare`, `ratio`, `filtered`). Модель путалась в
выборе. Slimming до одного tool с `mode` enum исправило.

### `/v1/chat/completions` для Gemma

OpenAI-compatible эндпоинт ломает tool calling в Gemma (и в qwen3.5
тоже флакает). Ollama native `/api/chat` стабильнее.

### LLM-роутер intent="data|knowledge"

Классификатор намерений добавлял 1–3 секунды латентности на КАЖДЫЙ
запрос, при том что 95%+ запросов — `data`. Удалили роутер; для
будущих knowledge-вопросов будет отдельный явный эндпоинт.

### Hardcoded skip-lists в нескольких местах

`_FALLBACK_TECHNICAL = {"Показатель_номер", ...}` лежал в одном
месте (`tool_defs.py`), но проверка `dim.get("technical")` в
`tool_caller.py` его не использовала — fallback не срабатывал.
Фикс — выделить helper `is_technical_dim(dim)` и переиспользовать
во всех точках. Правило: «правило в двух местах → helper».

## Архитектурные паттерны

### Move-to-platform

Текст 1С-запроса собирался в Python (`query_builder.py`), отправлялся
строкой в HTTP-сервис 1С. Перенос: Python отправляет ТОЛЬКО JSON-
параметры, 1С собирает запрос на BSL внутри. Польза:
- Безопасность: нет инъекций (текст запроса не приходит извне)
- Корректность синтаксиса: BSL гарантирует валидный 1С-синтаксис
- 5B модель не справлялась с генерацией Cyrillic 1C-запроса целиком

Это load-bearing rule всего проекта.

### Template formatter > LLM formatter

LLM-форматтер ответа был раньше в data flow. Заменили на шаблоны
(`answer_formatter.py` без LLM):
- −1 LLM round-trip = −1.5–3 сек на запрос
- Детерминированный вывод
- Покрывается обычными pytest-тестами

### Helper для cross-cutting concerns

Если правило фильтрации/проверки используется в N местах — не
дублировать. `is_technical_dim()` объединил три разрозненные
проверки, каждая из которых имела чуть-чуть другую логику.

## 1С HTTP-сервис — gotchas (записать в wiki как [[1c-http-service-design]])

### URL-шаблоны односегментные

В 1С HTTP-сервисе шаблон URL = одно имя после корня сервиса.
Запрещено: `/analytics/execute`, `/api/v1/foo`. Разрешено:
`/analytics_execute`, `/query`. Если нужен namespace — через
подчёркивание.

Грабли: переименовывали `/analytics/execute` → `/analytics_execute`
УЖЕ после публикации.

### РегистрСведений: три коллекции метаданных

`Измерения`, `Ресурсы`, `Реквизиты`. В разных конфигурациях числовые
поля типа «Сумма» лежат в `Ресурсы` либо `Реквизиты`. Валидатор
ресурса должен проверять ОБЕ коллекции:

```bsl
Найден = МетаРегистр.Ресурсы.Найти(Имя) <> Неопределено
      ИЛИ МетаРегистр.Реквизиты.Найти(Имя) <> Неопределено;
```

### BSL reserved words

`Знач` (модификатор pass-by-value), `Строка` (глобальная функция).
Не использовать как имена переменных. Альтернативы: `Элемент`,
`Запись`. Для конвертации — `XMLСтрока(value)` если есть переменная
`Строка`.

### Switch/case для операторов сравнения

Динамические операторы (`>`, `<`, `>=`, `=`) подставлять через
`Если`-цепочку, не конкатенацией строки — защита от инъекций при
небрежной валидации.

## Process anti-patterns (наблюдения о работе с Claude Code)

### «Claimed success без end-to-end verification»

После каждого крупного коммита следующая сессия открывалась с
«почему не работает X». Тесты зелёные, но веб не возвращает ответ.
Skill `superpowers:verification-before-completion` существовал, но
систематически не использовался. Правило: рестартанул сервис —
зашёл в браузер — задал реальный вопрос — только тогда «готово».

### Scope creep fix → refactor

«Поправь баг» превращалось в «давай заодно вынесу helper и обновлю
README и почистим dead code». Иногда это правильно (сегодняшний
−1736 строк cleanup), но чаще растягивает PR на 5× и теряет фокус.

### Премaturные commits на foundational choices

Модель `qwen3.5:4b → gemma4:e2b → qwen3.5:4b`. Tool count `4 → 7 →
1`. Query construction location `Python → 1C`. Каждый раз решение
принималось без бенчмарка/прототипа. Лучше: один спайк на 30 минут,
бенчмарк, потом коммит на архитектуру.

### Infrastructure yak-shaving в начале сессий

WSL proxy, Ollama-порты (11434 vs 11443), Open WebUI keys, curl
quoting, 1С URL slash. Перед задачей съедало 30+ минут. Лекарство:
memory entries (`reference_ollama_proxy.md`, `reference_model_config.md`),
которые автоматически подгружаются.

### Repeat correction: правило приходится повторять 3×

«В 1С URL без слеша» исправлялось в одной сессии трижды. Причина:
после первой коррекции не обновили все источники истины (код +
spec + README + actual published service) одновременно. Лекарство:
коррекция = sweep по всем источникам сразу + memory entry, чтобы
будущие сессии знали.

## Insights / surprises

### Self-healing с validation feedback дешёвый и работает

Один extra round-trip в LLM с message «вот предыдущие args, вот
ошибки, исправь» — и модель часто корректирует сама. На degraded
input baseline 11/12 → дополнительные кейсы автоматически
восстановились в 2/6. Дёшево, интерпретируемо, отлично для
production.

### Move-to-platform убирает целые классы багов

Когда query собирается на стороне платформы (1С), исчезают:
- Инъекции
- Синтаксические ошибки
- Несоответствие схемы (платформа сама проверяет имена полей)
- Cyrillic encoding issues в HTTP body

Стоимость: BSL-код становится толще. Но он толще И типизированнее
И тестируется руками 1С-специалиста.

### Metadata interview (sync_metadata.py) > hardcoded списки

Интерактивный режим в `sync_metadata.py`: прошёл по новым
измерениям, ответил «техническое / нет», «role: filter|group_by|both»,
«description_en». Метаданные пишутся в SQLite, tool_defs читает.
Заменяет hardcoded `_FALLBACK_TECHNICAL` для новых регистров.

### Cleanup-pass даёт ratio −10×

Один cleanup-коммит после 4 дней работы: −1736 / +149. Закономерность:
«первые 3 дня растут все компоненты на всякий случай (router, wiki,
query_generator, query_templates, formatter, llm_client, date_parser),
четвёртый день вырезаем 80%, потому что они не нужны». Лекарство:
аудит мёртвого кода каждые 2-3 крупные feature, а не раз в неделю.

## Концепции для wiki (curator hints)

Эти страницы стоит создать/обновить в `wiki/` при INGEST:

- `[[slm-tool-calling]]` — общая страница про tool calling в малых моделях
- `[[ollama-native-api-vs-openai-compat]]` — почему `/api/chat` лучше `/v1/...`
- `[[json-schema-design-for-small-models]]` — латинские ключи, enum, дефолты
- `[[self-healing-llm-loop]]` — паттерн validation-feedback-retry
- `[[1c-http-service-design]]` — URL templates, метаданные регистров, BSL
- `[[move-logic-to-platform]]` — архитектурный паттерн (генерация запроса на стороне БД/платформы)
- `[[metadata-driven-tool-schema]]` — динамическая схема из metadata
- `[[template-formatter-vs-llm-formatter]]` — когда LLM в форматтере НЕ нужен
- `[[claude-code-anti-patterns]]` — process-уроки работы с агентом
- `[[infrastructure-yak-shaving]]` — паттерн потери времени на инфру

## Источники в исходном репо

- `git log` коммиты `225a5e6`, `cb34c00`, `8462f1d`, `6fe234b`
- `docs/decisions/2026-04-12-self-healing.md`
- `docs/superpowers/specs/2026-04-10-smart-1c-backend-design.md`
- `docs/plans/2026-04-11-single-query-tool-design.md`
- Memory entries: URL templates, model config, ollama proxy
```

- [ ] **Step 2: Проверить длину файла**

Run: `wc -l "/mnt/c/Users/Admin/Projects/obsidian-llm-wiki/raw/2026-04-13-1c-analytics-slm-tool-calling-retrospective.md"`
Expected: 200–400 строк (плотный текст, без пустых блоков).

- [ ] **Step 3: Проверить наличие kebab-case wikilinks**

Run: `grep -c '\[\[[a-z][a-z0-9-]*\]\]' "/mnt/c/Users/Admin/Projects/obsidian-llm-wiki/raw/2026-04-13-1c-analytics-slm-tool-calling-retrospective.md"`
Expected: ≥ 7 (по acceptance criteria spec'а).

- [ ] **Step 4: Сообщить пользователю**

Текстовое сообщение пользователю:
> Raw-файл создан в `/mnt/c/Users/Admin/Projects/obsidian-llm-wiki/raw/2026-04-13-1c-analytics-slm-tool-calling-retrospective.md`.
> Это другое git-репо (vault'а). Я НЕ коммитил его — реши сам, когда будешь готов запускать INGEST в curator-сессии.

---

## Финальная верификация

### Task 3: Acceptance criteria check

- [ ] **Step 1: CLAUDE.md ≤ 200 строк**

Run: `wc -l CLAUDE.md`
Expected: значение ≤ 200.

- [ ] **Step 2: Раздел Lessons содержит 11–14 правил**

Run: `awk '/## Lessons learned/,/## Modular Docs/' CLAUDE.md | grep -c '^- '`
Expected: число между 11 и 14 (по spec'у).

- [ ] **Step 3: Каждое правило связано с реальным инцидентом**

Manual check (нечего автоматизировать). Пройди по списку, для каждого правила вспомни — какой коммит / какая memory entry / какая часть retro его породила. Если правило не из реального инцидента — удалить.

Связи (для проверки):
- «Один tool с mode enum» ← коммит `f7320ed` (single query tool migration)
- «Латинские ключи» ← коммит `f7622d5` (Latin mappings)
- «.env vs docs» ← memory `reference_model_config.md`
- «Ollama native API» ← коммит `fe2a814`
- «query текст не пересекает сеть» ← spec `2026-04-10-smart-1c-backend-design.md`
- «правило в двух местах → helper» ← коммиты `cb34c00` + `6fe234b` (technical-dim фикс дважды)
- «не ставить LLM где работает шаблон» ← коммит `8633ff4` + `6fe234b`
- «root cause vs симптом» ← коммит `8462f1d` (валидатор Реквизиты vs Ресурсы)
- «URL односегментные» ← memory `feedback_1c_url_templates.md` + коммит `225a5e6`
- «РегистрСведений 3 коллекции» ← коммит `8462f1d`
- «switch/case для операторов» ← spec, секция filtered tool
- «restart + реальный вопрос в вебе» ← из retro («claimed success без verification»)
- «коррекция → все источники истины» ← из retro («repeat correction 3×»)
- «untracked plan = долг» ← `docs/superpowers/plans/2026-04-08-metadata-and-validator.md` лежит untracked все 4 дня

- [ ] **Step 4: Raw-файл существует и читается Obsidian-конвенциями**

Run: `head -3 "/mnt/c/Users/Admin/Projects/obsidian-llm-wiki/raw/2026-04-13-1c-analytics-slm-tool-calling-retrospective.md"`
Expected: первая строка `# 1C Analytics AI Help — ретроспектива (4 дня, 2026-04-10…04-13)`. Нет YAML frontmatter (по конвенции raw/).

- [ ] **Step 5: Spec и CLAUDE.md закоммичены**

Run: `git log -1 --stat`
Expected: коммит «docs: add Lessons learned section to CLAUDE.md», файлы CLAUDE.md и spec.

- [ ] **Step 6: Финальный отчёт пользователю**

Текстовое сообщение:
> Готово. CLAUDE.md теперь N строк (предел 200), новый блок «Lessons learned» с M правилами. Раw-файл создан в vault'е, не закоммичен. Локальный коммит `<sha>` не запушен — пушить?

(N, M, sha — реальные значения из шагов 1, 2, 5.)

---

## Self-Review

**Spec coverage check:**
- ✅ Артефакт 1 (CLAUDE.md блок): Task 1
- ✅ Артефакт 2 (raw-файл): Task 2
- ✅ Acceptance criteria (`wc -l`, 11–14 правил, ≥7 wikilinks, не коммитить raw): Task 3 + явно в Task 1 step 5 / Task 2 step 4
- ✅ Что НЕ делаем: упомянуто, что raw не коммитится, глобальный CLAUDE.md не трогаем

**Placeholder scan:** нет TBD/TODO. Каждый шаг с конкретным кодом/командой/выводом.

**Type consistency:** имена файлов, путей и команд одинаковые во всех Task'ах. Дата-префикс `2026-04-13` единый. Имя raw-файла одинаково в spec'е и в этом плане.

**Implicit risks учтены:**
- Если vault недоступен (Windows mount отвалился) — Task 0 step 3 STOP-checkpoint
- Если git status не чист — Task 0 step 5 STOP-checkpoint
- Если CLAUDE.md превысит 200 — Task 1 step 2 STOP-checkpoint
