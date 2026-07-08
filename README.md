# v9.7 Cache de procesamiento

Esta versión evita que el sistema intente leer el Excel de 77 MB en cada carga.

Flujo:
1. Carga el Excel.
2. Presiona Procesar archivo.
3. La app guarda una copia procesada en data/cache.
4. Las siguientes cargas abren parquet/cache y son mucho más rápidas.

También aparece el botón "Procesar archivo activo" si ya hay archivo guardado pero falta procesarlo.
