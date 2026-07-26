# PS Operaciones Ropa v16.1 — Corrección de sesión

## Error corregido

Se corrigió:

`NameError: name 'hashlib' is not defined`

La función de sesión persistente utilizaba `hashlib.sha256()` sin importar
la librería en `app.py`.

## Cambios

- Se agregó `import hashlib`.
- Se agregó un import local de respaldo dentro de `_session_token_hash()`.
- Se validó la sintaxis de todos los archivos Python del proyecto.
- Se conservaron la sesión de 8 horas, el portal, la administración y los
  módulos de Conversión y Recuperación Económica.
