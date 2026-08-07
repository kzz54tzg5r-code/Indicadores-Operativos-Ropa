# PS Operaciones Ropa V40 — Estabilización de arranque

- Se agregaron checkpoints `[BOOT]`, `[PAGE]` y `[DATA]` visibles en logs de Streamlit Cloud.
- La restauración remota del Excel ahora es diferida: solo ocurre en páginas que requieren datos y cuando no existe archivo local.
- El timeout remoto bajó de 180 s a 12 s para impedir bloqueos prolongados.
- Si falla la fuente remota, el portal continúa abriendo y muestra la fuente como no disponible.
- Conexiones SQLite con timeout corto y `busy_timeout` para evitar bloqueos indefinidos.
- Se mantiene la versión de caché de datos para no obligar a reprocesar el Excel por un cambio visual.
- Lectura de datos conserva caché por página y añade medición de tiempo en logs.
- Se evita recalcular el SHA-256 del Excel repetidamente dentro de la misma sesión.
- Se añadió `.streamlit/config.toml` para desactivar el file watcher y reducir trabajo de arranque.
- No se modificaron fórmulas, KPIs ni reglas funcionales de V39.
