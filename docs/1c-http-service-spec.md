# 1С HTTP-сервис: спецификация эндпоинта /analytics/execute

## Назначение

Принимает JSON с именем инструмента и параметрами, собирает и выполняет
1С-запрос, возвращает результат в JSON.

## Эндпоинт

**POST** `/analytics/execute`

**Content-Type:** `application/json`
**Авторизация:** Basic Auth (те же credentials, что и для `/query`)

## Формат запроса

```json
{
  "register": "РегистрСведений.Витрина_Дашборда",
  "tool": "aggregate | group_by | top_n | time_series | compare | ratio | filtered",
  "params": {
    "resource": "Сумма",
    "filters": {
      "Сценарий": "Факт",
      "КонтурПоказателя": "свод",
      "Показатель": "Выручка",
      "ДЗО": "Консолидация"
    },
    "period": {
      "year": 2025,
      "month": 3
    },
    "group_by": ["ДЗО"],
    "order_by": "desc",
    "limit": 1000,

    "compare_by": "Сценарий",
    "values": ["Факт", "План"],

    "numerator": "Маржа",
    "denominator": "Выручка",

    "condition_operator": ">",
    "condition_value": 100000000
  }
}
```

Поля `compare_by`/`values` — только для tool=compare.
Поля `numerator`/`denominator` — только для tool=ratio.
Поля `condition_operator`/`condition_value` — только для tool=filtered.

## Обработчики по инструментам

### aggregate

Простая агрегация:

```
ВЫБРАТЬ ПЕРВЫЕ <limit>
    СУММА(<resource>) КАК Значение
ИЗ
    <register>
ГДЕ
    <условия из filters + period>
УПОРЯДОЧИТЬ ПО Значение <order_by>
```

### group_by

Группировка по измерению:

```
ВЫБРАТЬ ПЕРВЫЕ <limit>
    <group_by>,
    СУММА(<resource>) КАК Значение
ИЗ
    <register>
ГДЕ
    <условия>
СГРУППИРОВАТЬ ПО <group_by>
УПОРЯДОЧИТЬ ПО Значение <order_by>
```

### top_n

То же, что group_by, но limit по умолчанию = 10.

### time_series

Группировка по ГОД() + МЕСЯЦ(). Period опционален.

```
ВЫБРАТЬ ПЕРВЫЕ <limit>
    ГОД(<date_dim>) КАК Год,
    МЕСЯЦ(<date_dim>) КАК Месяц,
    СУММА(<resource>) КАК Значение
ИЗ
    <register>
ГДЕ
    <условия без period>
СГРУППИРОВАТЬ ПО ГОД(<date_dim>), МЕСЯЦ(<date_dim>)
УПОРЯДОЧИТЬ ПО Год, Месяц
```

### compare

Сравнение двух значений одного измерения:

```
ВЫБРАТЬ ПЕРВЫЕ <limit>
    <compare_by>,
    СУММА(<resource>) КАК Значение
ИЗ
    <register>
ГДЕ
    <compare_by> В (&Значения)
    И <остальные условия>
СГРУППИРОВАТЬ ПО <compare_by>
```

Параметр `Значения` = массив `values`.

В ответе `computed`: `diff` (второе минус первое), `percent` ((diff / первое) * 100).

### ratio

Отношение двух показателей:

```
ВЫБРАТЬ ПЕРВЫЕ <limit>
    Показатель,
    СУММА(<resource>) КАК Значение
ИЗ
    <register>
ГДЕ
    Показатель В (&Значения)
    И <остальные условия>
СГРУППИРОВАТЬ ПО Показатель
```

Параметр `Значения` = `[numerator, denominator]`.

В ответе `computed`: `ratio` = значение numerator / значение denominator.
Проверка деления на ноль -> `error_type: "no_data"`.

### filtered

Фильтрация по значению агрегата (HAVING):

```
ВЫБРАТЬ ПЕРВЫЕ <limit>
    <group_by>,
    СУММА(<resource>) КАК Значение
ИЗ
    <register>
ГДЕ
    <условия>
СГРУППИРОВАТЬ ПО <group_by>
ИМЕЮЩИЕ СУММА(<resource>) <operator> &Порог
УПОРЯДОЧИТЬ ПО Значение <order_by>
```

**ВАЖНО:** оператор подставлять через switch/case, не конкатенацией:

```
Если Оператор = ">" Тогда
    ТекстУсловия = "СУММА(" + Ресурс + ") > &Порог";
ИначеЕсли Оператор = "<" Тогда
    ...
КонецЕсли;
```

## Формат ответа

### Успех

```json
{
  "success": true,
  "data": [{"Сценарий": "Факт", "Значение": 150000000}],
  "computed": {"diff": -50000000, "percent": -25.0},
  "query_text": "ВЫБРАТЬ ..."
}
```

`computed` — только для compare/ratio. Для остальных — `null`.
`query_text` — опционально, для отладки.

### Ошибка

```json
{
  "success": false,
  "error_type": "invalid_params | missing_params | no_data | execution_error",
  "error_message": "Человекочитаемое описание ошибки",
  "allowed_values": ["Факт", "План"]
}
```

`allowed_values` — только для `invalid_params`, иначе отсутствует.

## Общая функция: ПостроитьУсловияОтбора

Принимает `filters` (dict) и `period` ({year, month}).

Для каждого filter: `<имя> = &<имя>`
Для period: `ГОД(<date_dim>) = &Год И МЕСЯЦ(<date_dim>) = &Месяц`

Устанавливает параметры через `Запрос.УстановитьПараметр()`.

## Валидация

`ВалидироватьПараметры()` перед сборкой запроса:
- register существует
- Имена измерений/ресурсов в params соответствуют метаданным
- Значения filters проверяются против допустимых
- При ошибке: `{"success": false, "error_type": "invalid_params", ...}`
