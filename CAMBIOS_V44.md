# V44 — Estabilización de memoria en Streamlit Cloud

- Centro Ejecutivo ya no carga el histórico comercial completo (más de 1.3 millones de filas) en cada rerun.
- Centro Ejecutivo carga solo el mes seleccionado; el listado histórico de meses se obtiene leyendo únicamente la columna Fecha del caché.
- Reporte Semanal carga únicamente la semana ISO seleccionada.
- Reporte Mensual carga únicamente el mes seleccionado.
- Se eliminaron del `load_data_for_page` los objetos gigantes retenidos por `st.cache_data`, evitando duplicación de memoria durante reruns.
- Los selectores históricos siguen mostrando el rango completo disponible mediante metadatos ligeros.
- No se modificaron fórmulas FIFO, KPIs, permisos ni reglas de alcance.

Motivo: los logs mostraron que Centro Ejecutivo llegó a cargar op=9,458 y co=1,312,796 filas; en el rerun siguiente el health check perdió la conexión con el proceso, patrón compatible con presión de memoria / reinicio del worker.
