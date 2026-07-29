# V20X.3.2 — Corrección de navegación

- Corrige `KeyError: v20_sidebar_navigation`.
- Los callbacks usan `session_state.get()` con valor de respaldo.
- Inicializa de forma defensiva las claves del menú de escritorio y móvil.
- Tolera sesiones antiguas después de actualizar la aplicación.
- Conserva las etapas ya procesadas y la corrección del esquema Parquet.
