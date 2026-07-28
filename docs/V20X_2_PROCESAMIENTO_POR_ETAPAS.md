# PS Operaciones Ropa V20X.2 — Procesamiento por etapas

El archivo grande ya no se procesa completo en una sola ejecución.

## Etapas

1. Hojas operativas y Plantilla.
2. Una hoja comercial por ejecución.
3. Consolidación final del caché.

## Recuperación

- Cada etapa se guarda en `cache/staged_processing`.
- El avance se registra en `config/staged_processing.json`.
- Si Streamlit reinicia el servicio, el siguiente intento continúa desde la
  etapa pendiente.
- Los archivos parciales se eliminan al cargar una fuente diferente o al
  seleccionar Reiniciar etapas.

## Resultado

La memoria se libera entre etapas y el servidor no necesita conservar todo
el libro y todos los DataFrames al mismo tiempo.
