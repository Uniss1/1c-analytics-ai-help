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

- `РегистрСведений` has `Измерения`, `Ресурсы`, and `Реквизиты` (all three).
- `РегистрНакопления` has `Измерения` and `Ресурсы`.
- Validate a resource by checking BOTH `Ресурсы` and `Реквизиты` — depending
  on how the register was designed, numeric fields like `Сумма` may live in
  either collection:

  ```bsl
  Найден = МетаРегистр.Ресурсы.Найти(Имя) <> Неопределено
        ИЛИ МетаРегистр.Реквизиты.Найти(Имя) <> Неопределено;
  ```

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
