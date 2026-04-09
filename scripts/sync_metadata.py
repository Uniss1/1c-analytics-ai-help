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
        print(f"  {register_name}: ошибка — {result.get('error', '?')}")
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
    """Classify fields into dimensions and resources based on sample data."""
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

    register_names = [r["name"] for r in yaml_data.get("registers", [])]
    if not register_names:
        print("Нет регистров в registers.yaml. Добавьте хотя бы имена регистров.")
        sys.exit(1)

    # Test connection
    print("Подключение к 1С...")
    try:
        result = query_1c("ВЫБРАТЬ ПЕРВЫЕ 1 1 КАК Тест")
        if not result.get("success"):
            print(f"ОШИБКА: {result.get('error')}")
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
        dimensions, resources = classify_fields(sample)
        print(f"    Измерения: {[d['name'] for d in dimensions]}")
        print(f"    Ресурсы:   {[r['name'] for r in resources]}")

        # Distinct values for keyword-worthy dimensions
        distinct = {}
        for dim in dimensions:
            if dim["name"] in DIMENSION_KEYWORDS_FIELDS:
                values = get_distinct_values(name, dim["name"])
                if values:
                    distinct[dim["name"]] = values
                    preview = values[:5]
                    print(f"    {dim['name']}: {len(values)} шт — {preview}{'...' if len(values) > 5 else ''}")

        # Keep existing keywords from YAML
        existing_reg = next((r for r in yaml_data.get("registers", []) if r["name"] == name), None)
        existing_kw = existing_reg.get("keywords", []) if existing_reg else []

        keywords = generate_keywords(name, distinct, existing_kw)
        print(f"    Keywords ({len(keywords)}): {keywords[:10]}{'...' if len(keywords) > 10 else ''}")

        synced[name] = {
            "dimensions": [{"name": d["name"], "data_type": d["data_type"]} for d in dimensions],
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
