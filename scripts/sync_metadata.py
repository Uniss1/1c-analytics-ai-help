#!/usr/bin/env python3
"""Discover 1C registers and update registers.yaml + metadata.db.

Reads register names from registers.yaml, probes 1C HTTP service to discover
actual dimensions/resources, extracts distinct values as keywords,
writes back to registers.yaml, then seeds metadata.db.

Usage:
    python3 scripts/sync_metadata.py

Reads ONEC_BASE_URL, ONEC_USER, ONEC_PASSWORD from .env (or environment).
"""

import re
import sqlite3
import sys
from pathlib import Path

import httpx
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from api.config import settings

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "metadata.db"
YAML_PATH = ROOT / "registers.yaml"

# Fields that are numeric aggregatable values (resources)
KNOWN_RESOURCE_NAMES = {
    "Сумма", "Выручка", "ОЗП", "Количество", "Численность", "ФОТ",
    "Себестоимость", "Маржа", "Прибыль", "Затраты", "Доход", "Расход",
    "Значение", "Итого", "Бюджет", "Факт", "План", "Отклонение",
}

# Fields to skip (system/internal)
SKIP_FIELDS = {"номер_строки", "НомерСтроки", "Регистратор", "Активность", "ВидДвижения"}

# Dimension fields worth extracting distinct values for keywords
DIMENSION_KEYWORDS_FIELDS = {"Показатель", "ДЗО", "Сценарий", "КонтурПоказателя", "ПризнакДоход"}

# Known default values for specific dimensions
KNOWN_DEFAULTS = {
    "Сценарий": "Факт",
    "КонтурПоказателя": "свод",
}

# Max distinct values to consider a dimension enumerable
MAX_ENUM_VALUES = 50

# Suggested English descriptions for known dimension fields.
# Used as defaults in the interactive interview.
_SUGGESTED_DESCRIPTIONS: dict[str, str] = {
    "Сценарий": "scenario type (Факт, План, Прогноз)",
    "КонтурПоказателя": "data contour / aggregation level",
    "Показатель": "metric name (Выручка, Маржа, EBITDA)",
    "ДЗО": "company / subsidiary (ДЗО, организация)",
    "Подразделение": "department / business unit",
    "Масштаб": "display scale (тыс., млн.)",
    "Ед_изм": "unit of measure",
    "Показатель_номер": "metric sort order number",
    "Месяц": "month number",
    "ПризнакДоход": "income/expense flag",
}


def suggest_description(field_name: str, values: list[str] | None = None) -> str:
    """Suggest an English description for a dimension field."""
    if field_name in _SUGGESTED_DESCRIPTIONS:
        return _SUGGESTED_DESCRIPTIONS[field_name]
    # Unknown field: generate from name + sample values
    vals_str = f" ({', '.join(values[:5])})" if values else ""
    return f"{field_name}{vals_str}"


def interview_dimension(dim: dict) -> dict:
    """Interactive interview for one dimension field.

    Shows field info and asks operator 1-3 questions.
    Returns dict with keys: technical, role (optional), description_en (optional).
    """
    name = dim["name"]
    dtype = dim.get("data_type", "?")
    values = dim.get("values", [])
    values_str = f", значения: {', '.join(str(v) for v in values[:10])}" if values else ""

    print(f'\nПоле "{name}" ({dtype}{values_str})')

    # Question 1: Technical?
    answer = input("  Техническое поле? (скрыть от модели) [y/n]: ").strip().lower()
    if answer in ("y", "yes", "д", "да"):
        return {"technical": True}

    # Question 2: Role
    print(f'  Роль поля "{name}":')
    print("    f — только фильтр (WHERE)")
    print("    g — только группировка (GROUP BY)")
    print("    b — и фильтр, и группировка")
    role_input = input("  [f/g/b]: ").strip().lower()
    role_map = {"f": "filter", "g": "group_by", "b": "both"}
    role = role_map.get(role_input, "filter")

    # Question 3: English description
    suggestion = suggest_description(name, values)
    desc_input = input(f'  Описание (EN): "{suggestion}"\n  [Enter — принять / текст — заменить]: ').strip()
    description_en = desc_input if desc_input else suggestion

    return {"technical": False, "role": role, "description_en": description_en}


def query_1c(query_text: str, params: dict | None = None) -> dict:
    """Execute query via 1C HTTP service."""
    url = f"{settings.onec_base_url}/query"
    with httpx.Client(timeout=60, auth=(settings.onec_user, settings.onec_password)) as client:
        resp = client.post(url, json={"query": query_text, "params": params or {}})
        resp.raise_for_status()
        return resp.json()


def probe_register(register_name: str) -> dict | None:
    """Try to query a register, return first row or None if doesn't exist."""
    try:
        result = query_1c(f"ВЫБРАТЬ ПЕРВЫЕ 1 * ИЗ {register_name}")
        if result.get("success") and result.get("data"):
            return result["data"][0]
        if result.get("success"):
            print(f"  {register_name}: пустой (0 строк)")
            return {}
        err = result.get("error_message") or result.get("error") or "?"
        print(f"  {register_name}: ошибка — {err}")
        return None
    except Exception as e:
        print(f"  {register_name}: не найден ({e})")
        return None


def get_distinct_values(register_name: str, field: str, limit: int = 200) -> list[str]:
    """Get distinct values of a dimension field."""
    try:
        result = query_1c(
            f"ВЫБРАТЬ РАЗЛИЧНЫЕ ПЕРВЫЕ {limit} {field} ИЗ {register_name}"
        )
        if result.get("success") and result.get("data"):
            return [str(row.get(field, "")) for row in result["data"] if row.get(field)]
        return []
    except Exception:
        return []


def classify_fields(sample_row: dict) -> tuple[list[dict], list[dict]]:
    """Classify fields into dimensions and resources based on sample data (simple format)."""
    dimensions = []
    resources = []

    for field_name, value in sample_row.items():
        if field_name in SKIP_FIELDS:
            continue

        if isinstance(value, (int, float)) and field_name in KNOWN_RESOURCE_NAMES:
            resources.append({"name": field_name, "data_type": "Число", "description": ""})
        elif isinstance(value, str) and "T" in value and len(value) >= 19:
            dimensions.append({"name": field_name, "data_type": "Дата", "description": ""})
        elif isinstance(value, (int, float)) and field_name not in DIMENSION_KEYWORDS_FIELDS:
            if any(kw in field_name.lower() for kw in ("месяц", "номер", "код")):
                dimensions.append({"name": field_name, "data_type": "Число", "description": ""})
            else:
                resources.append({"name": field_name, "data_type": "Число", "description": ""})
        else:
            dimensions.append({"name": field_name, "data_type": "Строка", "description": ""})

    return dimensions, resources


def classify_fields_enriched(
    sample_row: dict, register_name: str
) -> tuple[list[dict], list[dict]]:
    """Classify fields into enriched dimensions and resources.

    Enriched dimensions include: required, default, filter_type, values.
    For string/enum dimensions, queries 1C for distinct values.
    """
    dimensions = []
    resources = []

    for field_name, value in sample_row.items():
        if field_name in SKIP_FIELDS:
            continue

        # Resource: numeric field with known resource name
        if isinstance(value, (int, float)) and field_name in KNOWN_RESOURCE_NAMES:
            resources.append({"name": field_name})
            continue

        # Date field
        if isinstance(value, str) and "T" in value and len(value) >= 19:
            dimensions.append({
                "name": field_name,
                "data_type": "Дата",
                "required": True,
                "default": None,
                "filter_type": "year_month",
            })
            continue

        # Numeric field that looks like a dimension (Месяц, Код, etc.)
        if isinstance(value, (int, float)) and field_name not in DIMENSION_KEYWORDS_FIELDS:
            if any(kw in field_name.lower() for kw in ("месяц", "номер", "код")):
                dimensions.append({
                    "name": field_name,
                    "data_type": "Число",
                    "required": False,
                    "default": None,
                    "filter_type": "=",
                })
                continue
            else:
                # Numeric but not a dimension pattern — treat as resource
                resources.append({"name": field_name})
                continue

        # String/enum dimension — query 1C for distinct values
        distinct_values = get_distinct_values(register_name, field_name, limit=MAX_ENUM_VALUES + 1)
        is_enum = 0 < len(distinct_values) <= MAX_ENUM_VALUES

        dim = {
            "name": field_name,
            "data_type": "Строка",
            "required": is_enum,
            "default": KNOWN_DEFAULTS.get(field_name),
            "filter_type": "=",
        }
        if is_enum:
            dim["values"] = distinct_values

        dimensions.append(dim)

    return dimensions, resources


def generate_keywords(register_name: str, distinct_values: dict, existing_keywords: list[str]) -> list[str]:
    """Generate search keywords from register name, dimension values, and keep existing."""
    keywords = set(existing_keywords)

    # From register name: ВитринаВыручка → выручка
    short_name = register_name.split(".")[-1]
    parts = re.findall(r"[А-ЯЁ][а-яё]+", short_name)
    for part in parts:
        kw = part.lower()
        if kw not in ("витрина", "регистр", "накопления"):
            keywords.add(kw)

    # From distinct values of key fields
    for field, values in distinct_values.items():
        for val in values:
            kw = val.strip().lower()
            if len(kw) >= 2 and kw not in ("", "-", "0"):
                keywords.add(kw)

    return sorted(keywords)


def update_yaml(yaml_data: dict, synced: dict) -> dict:
    """Update registers in yaml_data with discovered metadata from 1C."""
    reg_by_name = {r["name"]: r for r in yaml_data.get("registers", [])}

    for reg_name, info in synced.items():
        if reg_name in reg_by_name:
            # Update existing register
            reg = reg_by_name[reg_name]
            reg["dimensions"] = info["dimensions"]
            reg["resources"] = info["resources"]
            reg["keywords"] = info["keywords"]
        else:
            # Add new register discovered from 1C
            yaml_data.setdefault("registers", []).append({
                "name": reg_name,
                "description": reg_name.split(".")[-1],
                "type": "accumulation_turnover",
                "dimensions": info["dimensions"],
                "resources": info["resources"],
                "keywords": info["keywords"],
            })

    return yaml_data


def normalize_yaml(yaml_data: dict) -> tuple[dict, list[str]]:
    """Normalize registers list: support both simple strings and full dicts.

    Simple format:   registers: ["РегистрНакопления.Foo", "РегистрНакопления.Bar"]
    Full format:     registers: [{name: "...", dimensions: [...], ...}]

    Returns (normalized_yaml_data, register_names).
    """
    raw = yaml_data.get("registers", [])
    if not raw:
        return yaml_data, []

    names = []
    normalized = []
    for item in raw:
        if isinstance(item, str):
            names.append(item)
            normalized.append({
                "name": item,
                "description": item.split(".")[-1],
                "type": "accumulation_turnover",
            })
        elif isinstance(item, dict):
            names.append(item["name"])
            normalized.append(item)

    yaml_data["registers"] = normalized
    return yaml_data, names


def main():
    print(f"1C: {settings.onec_base_url}")
    print(f"User: {settings.onec_user}")
    print(f"DB: {DB_PATH}")
    print(f"YAML: {YAML_PATH}\n")

    # Load existing YAML
    if YAML_PATH.exists():
        with open(YAML_PATH, encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f) or {}
    else:
        yaml_data = {"dashboards": [], "registers": []}

    yaml_data, register_names = normalize_yaml(yaml_data)
    if not register_names:
        print("Нет регистров в registers.yaml. Добавьте хотя бы имена регистров.")
        sys.exit(1)

    # Test connection
    print("Подключение к 1С...")
    try:
        result = query_1c("ВЫБРАТЬ ПЕРВЫЕ 1 1 КАК Тест")
        if not result.get("success"):
            err = result.get("error_message") or result.get("error") or "?"
            print(f"ОШИБКА: {err}")
            sys.exit(1)
        print("OK\n")
    except Exception as e:
        print(f"ОШИБКА: {e}")
        sys.exit(1)

    # Probe registers
    print("Поиск регистров...")
    synced = {}
    for name in register_names:
        sample = probe_register(name)
        if sample is None:
            continue
        if not sample:
            print(f"  ⚠ {name}: пустой, пропускаю")
            continue

        print(f"  ✓ {name} — {len(sample)} полей")
        dimensions, resources = classify_fields_enriched(sample, name)
        print(f"    Измерения: {[d['name'] for d in dimensions]}")
        print(f"    Ресурсы:   {[r['name'] for r in resources]}")

        # Print enriched info
        for dim in dimensions:
            extras = []
            if dim.get("required"):
                extras.append("required")
            if dim.get("default"):
                extras.append(f"default={dim['default']}")
            if dim.get("values"):
                extras.append(f"{len(dim['values'])} values")
            if dim.get("filter_type") and dim["filter_type"] != "=":
                extras.append(f"filter={dim['filter_type']}")
            if extras:
                print(f"    {dim['name']}: {', '.join(extras)}")

        # Look up existing register config from YAML (for interview skip logic)
        existing_reg = next((r for r in yaml_data.get("registers", []) if isinstance(r, dict) and r.get("name") == name), None)

        # Interactive interview: ask operator about each dimension
        print(f"\n  --- Интервью по измерениям {name} ---")
        for dim in dimensions:
            # Skip date dimensions — always handled by year/month
            if dim.get("filter_type") == "year_month":
                print(f'  [auto] "{dim["name"]}" — дата, пропускаю')
                continue

            # Check if YAML already has annotations for this field
            existing_dim = None
            if existing_reg:
                existing_dim = next(
                    (d for d in existing_reg.get("dimensions", [])
                     if isinstance(d, dict) and d.get("name") == dim["name"]),
                    None,
                )

            if existing_dim and "technical" in existing_dim:
                # Already annotated — show and skip
                tech = existing_dim.get("technical", False)
                role = existing_dim.get("role", "filter")
                desc = existing_dim.get("description_en", "")
                status = "техн." if tech else f"role={role}"
                print(f'  [yaml] "{dim["name"]}" — {status}, "{desc}"')
                dim["technical"] = tech
                if not tech:
                    dim["role"] = role
                    dim["description_en"] = desc
                continue

            # Interview this dimension
            annotations = interview_dimension(dim)
            dim["technical"] = annotations.get("technical", False)
            if not dim["technical"]:
                dim["role"] = annotations.get("role", "filter")
                dim["description_en"] = annotations.get("description_en")

        # Distinct values for keyword generation (use values already discovered)
        distinct = {}
        for dim in dimensions:
            if dim["name"] in DIMENSION_KEYWORDS_FIELDS and dim.get("values"):
                distinct[dim["name"]] = dim["values"]

        # Keep existing keywords from YAML (if any)
        existing_reg = next((r for r in yaml_data.get("registers", []) if isinstance(r, dict) and r.get("name") == name), None)
        existing_kw = existing_reg.get("keywords", []) if existing_reg else []

        keywords = generate_keywords(name, distinct, existing_kw)
        print(f"    Keywords ({len(keywords)}): {keywords[:10]}{'...' if len(keywords) > 10 else ''}")

        # Build enriched dimension dicts for YAML
        enriched_dims = []
        for d in dimensions:
            dim_dict = {"name": d["name"], "data_type": d["data_type"]}
            dim_dict["required"] = d.get("required", False)
            dim_dict["default"] = d.get("default")
            if d.get("filter_type") and d["filter_type"] != "=":
                dim_dict["filter_type"] = d["filter_type"]
            if d.get("values"):
                dim_dict["values"] = d["values"]
            # New annotation fields
            if "technical" in d:
                dim_dict["technical"] = d["technical"]
            if d.get("role"):
                dim_dict["role"] = d["role"]
            if d.get("description_en"):
                dim_dict["description_en"] = d["description_en"]
            enriched_dims.append(dim_dict)

        synced[name] = {
            "dimensions": enriched_dims,
            "resources": [{"name": r["name"]} for r in resources],
            "keywords": keywords,
        }

    if not synced:
        print("\nНе удалось получить данные ни по одному регистру.")
        sys.exit(1)

    print(f"\nСинхронизировано: {len(synced)}\n")

    # Update YAML
    yaml_data = update_yaml(yaml_data, synced)
    with open(YAML_PATH, "w", encoding="utf-8") as f:
        yaml.dump(yaml_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    print(f"registers.yaml обновлён")

    # Seed metadata.db from updated YAML
    from scripts.seed_metadata import create_schema, seed_from_yaml
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON")
    create_schema(cur)
    seed_from_yaml(cur, yaml_data)
    conn.commit()
    conn.close()
    print(f"metadata.db обновлён")

    print("\nГотово. Проверка:")
    print(f"  cat registers.yaml")
    print(f"  sqlite3 {DB_PATH} 'SELECT name FROM registers'")


if __name__ == "__main__":
    main()
