"""Persistencia local, historial de fuentes y respaldos del módulo comercial."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import zipfile

from .config import (
    ACTIONS_FILE,
    BACKUP_DIR,
    CAPACITY_DIR,
    DATA_ROOT,
    MANIFEST_FILE,
    PDF_DIR,
    SALES_DIR,
    ensure_directories,
)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _safe_name(name: str) -> str:
    clean = Path(str(name or "archivo")).name
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", clean).strip("._")
    return clean or "archivo"


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def load_manifest() -> dict:
    ensure_directories()
    default = {"version": 1, "sales": [], "capacities": [], "pdfs": [], "updated_at": ""}
    try:
        payload = json.loads(MANIFEST_FILE.read_text(encoding="utf-8")) if MANIFEST_FILE.exists() else default
        if not isinstance(payload, dict):
            payload = default
    except Exception:
        payload = default
    payload = {**default, **payload}
    for key in ("sales", "capacities", "pdfs"):
        if not isinstance(payload.get(key), list):
            payload[key] = []
    return discover_existing_files(payload)


def save_manifest(payload: dict) -> None:
    payload = dict(payload)
    payload["updated_at"] = _now()
    _atomic_json(MANIFEST_FILE, payload)


def discover_existing_files(manifest: dict | None = None) -> dict:
    """Registra archivos incluidos en el proyecto sin duplicar entradas."""
    ensure_directories()
    manifest = dict(manifest or {"version": 1, "sales": [], "capacities": [], "pdfs": []})
    for key in ("sales", "capacities", "pdfs"):
        manifest.setdefault(key, [])
    known = {
        str(item.get("path", ""))
        for key in ("sales", "capacities", "pdfs")
        for item in manifest.get(key, [])
    }
    roots = [
        ("sales", SALES_DIR, {".xlsx", ".xls", ".csv"}),
        ("capacities", CAPACITY_DIR, {".xlsx", ".xls", ".csv"}),
        ("pdfs", PDF_DIR, {".pdf"}),
    ]
    changed = False
    for key, root, extensions in roots:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in extensions:
                continue
            relative = str(path.relative_to(DATA_ROOT))
            if relative in known:
                continue
            manifest[key].append({
                "id": _file_hash(path)[:16],
                "name": path.name,
                "path": relative,
                "sha256": _file_hash(path),
                "size": path.stat().st_size,
                "uploaded_at": datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
                "status": "Pendiente de validación",
            })
            known.add(relative)
            changed = True
    if changed:
        save_manifest(manifest)
    return manifest


def resolve_entry_path(entry: dict) -> Path:
    return DATA_ROOT / str(entry.get("path", ""))


def _uploaded_bytes(uploaded) -> bytes:
    if hasattr(uploaded, "getvalue"):
        return bytes(uploaded.getvalue())
    if hasattr(uploaded, "getbuffer"):
        return bytes(uploaded.getbuffer())
    data = uploaded.read()
    return bytes(data)


def _save_source(uploaded, category: str, destination: Path, subfolder: str | None = None) -> dict:
    ensure_directories()
    data = _uploaded_bytes(uploaded)
    digest = sha256(data).hexdigest()
    manifest = load_manifest()
    existing = next((item for item in manifest[category] if item.get("sha256") == digest), None)
    if existing:
        return {**existing, "duplicate": True}

    target_dir = destination / subfolder if subfolder else destination
    target_dir.mkdir(parents=True, exist_ok=True)
    base_name = _safe_name(getattr(uploaded, "name", "archivo"))
    target = target_dir / base_name
    if target.exists():
        target = target.with_name(f"{target.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{target.suffix}")
    target.write_bytes(data)
    entry = {
        "id": digest[:16],
        "name": target.name,
        "path": str(target.relative_to(DATA_ROOT)),
        "sha256": digest,
        "size": len(data),
        "uploaded_at": _now(),
        "status": "Pendiente de validación",
    }
    manifest[category].append(entry)
    save_manifest(manifest)
    return {**entry, "duplicate": False}


def save_sales_upload(uploaded) -> dict:
    return _save_source(uploaded, "sales", SALES_DIR)


def save_capacity_upload(uploaded) -> dict:
    return _save_source(uploaded, "capacities", CAPACITY_DIR)


def save_pdf_upload(uploaded, week_key: str) -> dict:
    entry = _save_source(uploaded, "pdfs", PDF_DIR, _safe_name(week_key))
    manifest = load_manifest()
    for item in manifest["pdfs"]:
        if item.get("id") == entry.get("id"):
            item["week"] = week_key
            entry["week"] = week_key
    save_manifest(manifest)
    return entry


def update_entry(category: str, entry_id: str, **changes) -> None:
    manifest = load_manifest()
    for item in manifest.get(category, []):
        if item.get("id") == entry_id:
            item.update(changes)
            break
    save_manifest(manifest)


def latest_entry(category: str) -> dict | None:
    entries = [item for item in load_manifest().get(category, []) if resolve_entry_path(item).exists()]
    if not entries:
        return None
    return max(entries, key=lambda item: str(item.get("uploaded_at", "")))


def load_actions() -> list[dict]:
    try:
        data = json.loads(ACTIONS_FILE.read_text(encoding="utf-8")) if ACTIONS_FILE.exists() else []
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_actions(actions: list[dict]) -> None:
    _atomic_json(ACTIONS_FILE, actions)


def build_history_backup() -> bytes:
    """Genera un ZIP recuperable con fuentes, manifiesto y acciones."""
    ensure_directories()
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(DATA_ROOT.rglob("*")):
            if not path.is_file() or CACHE_DIR_NAME in path.parts:
                continue
            archive.write(path, arcname=str(path.relative_to(DATA_ROOT)))
    output.seek(0)
    return output.getvalue()


CACHE_DIR_NAME = "cache"


def restore_history_backup(uploaded) -> int:
    """Restaura un respaldo sin borrar las fuentes que ya existen."""
    data = _uploaded_bytes(uploaded)
    restored = 0
    with zipfile.ZipFile(BytesIO(data)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            relative = Path(info.filename)
            if relative.is_absolute() or ".." in relative.parts:
                continue
            target = DATA_ROOT / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(archive.read(info))
                restored += 1
    discover_existing_files(load_manifest())
    return restored
