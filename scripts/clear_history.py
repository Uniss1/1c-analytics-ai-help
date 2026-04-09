#!/usr/bin/env python3
"""Clear history.db — remove all sessions, messages, and cached responses."""

import os
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "history.db"

if DB_PATH.exists():
    os.remove(DB_PATH)
    print(f"Удалён: {DB_PATH}")
else:
    print(f"Файл не найден: {DB_PATH}")

print("history.db будет пересоздан при следующем запуске FastAPI.")
