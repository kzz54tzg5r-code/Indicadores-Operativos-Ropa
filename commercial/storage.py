"""Persistencia local, historial de fuentes y respaldos del módulo comercial."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from io import BytesIO
import json
import mimetypes
import os
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
import zipfile

from .config import (
    ACTIONS_FILE,
    BACKUP_DIR,
    CAPACITY_DIR,
    DATA_ROOT,
    MANIFEST_FILE,
    PDF_DIR,
    SALES_DIR,
    SNAPSHOTS_FILE,
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


def _setting(name: str, default: str = "") -> str:
    """Lee una configuración sin obligar a importar Streamlit en las pruebas."""
    value = os.getenv(name, "")
    if value:
        return str(value).strip()
    try:
        import streamlit as st

        value = st.secrets.get(name, default)
    except Exception:
        value = default
    return str(value or "").strip()


def cloud_configuration() -> dict:
    """Configuración opcional de un bucket privado de Supabase Storage."""
    return {
        "url": _setting("PS_COMMERCIAL_SUPABASE_URL").rstrip("/"),
        "key": _setting("PS_COMMERCIAL_SUPABASE_KEY"),
        "bucket": _setting("PS_COMMERCIAL_SUPABASE_BUCKET", "ps-operaciones-private"),
        "prefix": _setting("PS_COMMERCIAL_SUPABASE_PREFIX", "commercial").strip("/"),
    }


def cloud_enabled() -> bool:
    config = cloud_configuration()
    return bool(config["url"] and config["key"] and config["bucket"])


def _cloud_object_url(relative: str) -> tuple[str, dict]:
    config = cloud_configuration()
    object_name = "/".join(part for part in (config["prefix"], relative.strip("/")) if part)
    encoded = quote(object_name, safe="/")
    url = f"{config['url']}/storage/v1/object/{quote(config['bucket'], safe='')}/{encoded}"
    headers = {
        "Authorization": f"Bearer {config['key']}",
        "apikey": config["key"],
    }
    return url, headers


def _cloud_download(relative: str) -> bytes | None:
    if not cloud_enabled():
        return None
    url, headers = _cloud_object_url(relative)
    try:
        with urlopen(Request(url, headers=headers), timeout=25) as response:
            return response.read()
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def _cloud_upload(relative: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    url, headers = _cloud_object_url(relative)
    headers.update({"Content-Type": content_type, "x-upsert": "true"})
    request = Request(url, data=data, headers=headers, method="POST")
    with urlopen(request, timeout=90) as response:
        response.read()


def load_snapshots() -> dict[str, dict]:
    try:
        payload = json.loads(SNAPSHOTS_FILE.read_text(encoding="utf-8")) if SNAPSHOTS_FILE.exists() else {}
    except Exception:
        payload = {}
    if isinstance(payload, dict) and isinstance(payload.get("items"), dict):
        return payload["items"]
    return payload if isinstance(payload, dict) else {}


def save_snapshot(entry_id: str, snapshot: dict) -> None:
    items = load_snapshots()
    items[str(entry_id)] = dict(snapshot)
    _atomic_json(SNAPSHOTS_FILE, {"version": 1, "updated_at": _now(), "items": items})


def restore_history_from_cloud() -> dict:
    """Restaura estado y fuentes tabulares; los PDF se leen desde su snapshot.

    Así el arranque no vuelve a descargar todos los PDF históricos, pero sus
    originales continúan resguardados en el bucket privado.
    """
    result = {"configured": cloud_enabled(), "restored": 0, "error": ""}
    if not result["configured"]:
        return result
    try:
        remote_manifest_data = _cloud_download("manifest.json")
        if not remote_manifest_data:
            return result
        remote_manifest = json.loads(remote_manifest_data.decode("utf-8"))
        local_manifest = load_manifest()
        merged = {"version": 1, "sales": [], "capacities": [], "pdfs": []}
        for category in ("sales", "capacities", "pdfs"):
            by_id = {
                str(item.get("id") or item.get("sha256")): dict(item)
                for item in local_manifest.get(category, [])
            }
            for item in remote_manifest.get(category, []):
                key = str(item.get("id") or item.get("sha256"))
                by_id[key] = {**by_id.get(key, {}), **dict(item)}
            merged[category] = list(by_id.values())
        save_manifest(merged)

        remote_snapshots = _cloud_download("snapshots.json")
        if remote_snapshots:
            payload = json.loads(remote_snapshots.decode("utf-8"))
            remote_items = payload.get("items", payload) if isinstance(payload, dict) else {}
            items = {**load_snapshots(), **(remote_items if isinstance(remote_items, dict) else {})}
            _atomic_json(SNAPSHOTS_FILE, {"version": 1, "updated_at": _now(), "items": items})

        remote_actions = _cloud_download("actions.json")
        if remote_actions and not ACTIONS_FILE.exists():
            ACTIONS_FILE.write_bytes(remote_actions)

        # Ventas y capacidades sí se restauran porque alimentan el análisis
        # por modelo. Los PDF históricos usan snapshots y no penalizan arranque.
        for category in ("sales", "capacities"):
            for entry in merged.get(category, []):
                target = resolve_entry_path(entry)
                if target.exists():
                    continue
                data = _cloud_download(str(entry.get("path", "")))
                if data:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                    result["restored"] += 1
        result["restored"] += len(load_snapshots())
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def sync_history_to_cloud(source_paths: list[Path] | None = None) -> dict:
    """Sincroniza fuentes nuevas y metadatos al bucket privado configurado."""
    result = {"configured": cloud_enabled(), "uploaded": 0, "error": ""}
    if not result["configured"]:
        return result
    try:
        unique_paths = []
        for path in source_paths or []:
            path = Path(path)
            if path.exists() and path.is_file() and path not in unique_paths:
                unique_paths.append(path)
        for path in unique_paths:
            relative = str(path.relative_to(DATA_ROOT))
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            _cloud_upload(relative, path.read_bytes(), content_type)
            result["uploaded"] += 1
        for path in (MANIFEST_FILE, SNAPSHOTS_FILE, ACTIONS_FILE):
            if path.exists():
                _cloud_upload(path.name, path.read_bytes(), "application/json")
        result["uploaded"] += 1
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


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
