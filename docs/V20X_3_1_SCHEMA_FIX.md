# V20X.3.1 — Corrección de consolidación Parquet

Se corrigió el error de esquema durante la etapa `finalize`.

- `Piezas` puede llegar como `int64` o `double` según la hoja.
- La consolidación ahora inspecciona todos los esquemas parciales.
- Los tipos numéricos mixtos se promueven a `float64`.
- Se eliminan diferencias de metadatos de pandas.
- Se escriben lotes de 25,000 filas para mantener bajo el consumo de memoria.
- Las etapas anteriores se conservan; basta volver a ejecutar `finalize`.
