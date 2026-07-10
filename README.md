# Indicadores Cambios y Muertos v10.31

Corrección principal:
- La fecha `2026-07-09 17:00:14` se estaba interpretando como `2026-09-07`.
- Por eso Diagnóstico mostraba la hoja nueva hasta septiembre y el reporte del 09/07/2026 tenía operación = 0.
- Ahora los formatos ISO con hora se interpretan siempre como:
  año-mes-día.

Resultado esperado:
- Resultados productividad 2:
  - fecha mínima: 2026-06-29
  - fecha máxima: 2026-07-09
- Al consultar 09/07/2026:
  - operación debe ser mayor que 0;
  - Acondicionado, Ubicado, Recolectadas, Muertos, Cajas y Probador deben mostrar valores reales.
- El Dashboard Ejecutivo vuelve a sumar el histórico y la hoja nueva.

Actualización obligatoria:
1. Sustituir los archivos del repositorio.
2. Reiniciar Streamlit.
3. Borrar el archivo persistido.
4. Cargar nuevamente el Excel.
5. Procesar el archivo.
6. Revisar que Diagnóstico muestre fecha máxima 2026-07-09, no 2026-09-07.
