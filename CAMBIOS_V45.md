# V45 — Recuperación de datos por periodo

- Corrige la lectura de rangos desde el caché Parquet cuando `Fecha` contiene hora o está almacenada con un tipo incompatible con el filtro nativo.
- El límite final de cada consulta ahora incluye todo el día seleccionado.
- Si Parquet no permite filtrar directamente, el archivo se recorre por lotes de 100,000 filas y solo se conservan las filas del periodo solicitado.
- Se elimina el fallback peligroso que abría todo el histórico comercial cuando un rango devolvía cero filas.
- Operación Diaria respeta la fecha elegida en el selector en cada rerun.
- Se conservan cálculos, alcance de tiendas, PDFs y estructura de reportes de V44.
