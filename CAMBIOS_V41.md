# PS Operaciones Ropa V41

## Cambios
- Centro Ejecutivo, Reporte Semanal y Reporte Mensual leen el histórico completo procesado para que los selectores incluyan meses desde abril cuando existan en la fuente.
- Recuperación usa el histórico comercial completo procesado.
- El PDF de cada pestaña toma los KPI reales del reporte, no un juego fijo de claves.
- El PDF incluye tarjetas KPI, tabla principal, tarjetas semanales del Centro Ejecutivo, tablas adicionales y gráficos operativos inferibles de los mismos datos usados en pantalla.
- Excel conserva resumen, detalle y hojas auxiliares del reporte.
- Se mantiene la estabilización de arranque V40.

## Validación
- 15 pruebas aprobadas.
- app.py, legacy_app.py y core/settings.py compilan.
