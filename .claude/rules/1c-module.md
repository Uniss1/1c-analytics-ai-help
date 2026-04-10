---
paths: "docs/1c-http-service-module.md"
---

# 1C BSL Code Rules

Common 1C compilation errors to avoid when writing BSL code:

## Reserved Words

- `Знач` — reserved keyword (pass-by-value modifier). Never use as variable name. Use `Элемент`, `Запись`, etc.
- `Строка` — global function `Строка()`. Don't shadow with `Строка = Новый Структура`. Use `Запись` instead.

## Metadata Access

- `Метаданные.РегистрыСведений[name]` — WRONG. Collections don't support bracket access.
- `Метаданные.РегистрыСведений.Найти(name)` — CORRECT. Returns `Неопределено` if not found.

## Query Results

- `Выборка[FieldName]` — WRONG. `ВыборкаИзРезультатаЗапроса` doesn't support indexed access by string.
- Use `Результат.Выгрузить()` → iterate `СтрокаТЗ[FieldName]` on `ТаблицаЗначений`.

## РегистрСведений vs РегистрНакопления

- `РегистрСведений` has `Реквизиты` and `Измерения`, NOT `Ресурсы`.
- `РегистрНакопления` has `Ресурсы`.
- Check resource in: `МетаРегистр.Реквизиты.Найти(name)`, not `Ресурсы`.

## Security: Operators

Always use switch/case for SQL operators, never string concatenation:

```bsl
Если Оператор = ">" Тогда
    ТекстОператора = ">";
ИначеЕсли Оператор = "<" Тогда
    ТекстОператора = "<";
// ...
КонецЕсли;
```

## Type Conversion

- `Строка(value)` may conflict with variable named `Строка`. Use `XMLСтрока(value)` for safe conversion.
