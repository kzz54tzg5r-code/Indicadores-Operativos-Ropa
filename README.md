# Indicadores Cambios y Muertos v11.1

## Regla corregida

Los indicadores generales ahora se calculan exactamente así:

- Pendientes por ubicar = Piezas ingresadas - Piezas ubicadas
- % Procesado = Piezas ubicadas / Piezas ingresadas × 100

Ejemplo:
- Piezas ingresadas: 150,886
- Piezas ubicadas: 115,511
- Pendientes por ubicar: 35,375
- % Procesado: 76.6%

La misma regla se refleja en:
- Dashboard Ejecutivo
- Por Día
- Reporte Semanal
- Reporte Mensual
- Tarjetas de pantalla
- Tarjetas de los PDF

## Actualización

1. Sustituye los archivos del repositorio.
2. Reinicia Streamlit.
3. No es necesario volver a procesar el Excel.
