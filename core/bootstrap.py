from __future__ import annotations
import logging
import time
from core.settings import DATA_DIR, UPLOAD_DIR, CACHE_DIR, CONFIG_DIR, REPORTS_DIR, LOG_DIR, BACKUP_DIR
from core.database import initialize_database

def initialize_application() -> None:
    started=time.perf_counter()
    for path in (DATA_DIR, UPLOAD_DIR, CACHE_DIR, CONFIG_DIR, REPORTS_DIR, LOG_DIR, BACKUP_DIR):
        path.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    print("[BOOT] directorios listos", flush=True)
    initialize_database()
    print(f"[BOOT] base de control lista en {time.perf_counter()-started:.2f}s", flush=True)
