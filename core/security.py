"""Funciones de seguridad y contraseñas.

Las contraseñas nuevas se almacenan con Argon2id. Los hashes SHA-256 heredados
se aceptan temporalmente para migración y se actualizan al iniciar sesión.
"""
from __future__ import annotations

import hashlib
import hmac
import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_PH = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)


def hash_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < 8:
        raise ValueError("La contraseña debe contener al menos 8 caracteres.")
    return _PH.hash(password)


def verify_password(password: str, stored_hash: str) -> tuple[bool, bool]:
    """Devuelve (válida, requiere_actualización_de_hash)."""
    stored_hash = str(stored_hash or "")
    if stored_hash.startswith("$argon2"):
        try:
            valid = _PH.verify(stored_hash, password)
            return bool(valid), bool(valid and _PH.check_needs_rehash(stored_hash))
        except (VerifyMismatchError, InvalidHashError):
            return False, False

    # Compatibilidad con la versión anterior.
    if _SHA256_RE.fullmatch(stored_hash):
        candidate = hashlib.sha256(str(password).encode("utf-8")).hexdigest()
        return hmac.compare_digest(candidate, stored_hash), True

    return False, False
