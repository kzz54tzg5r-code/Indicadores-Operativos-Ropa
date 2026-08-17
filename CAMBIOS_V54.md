# PS Operaciones Ropa V54 - Corrección de extracción PDF comercial

## Problema corregido

V53 conservaba el PDF original y su historial, pero no convertía las tablas del
documento en registros para los tableros. Esto provocaba ventas, utilidad y VPD
en cero cuando no estaba disponible el Excel mensual.

## Cambios

- Extracción real de tablas mediante `pdfplumber`.
- Normalización de sección, categoría, rubro y ubicación.
- Extracción de inventario, sugerido 7, VPD sugerida, DDI, DDC, brazos,
  posiciones y porcentajes de participación.
- Extracción de rankings por utilidad, sugerido, sugerido cero y mayor inversión.
- Cruce por tienda e `ID_ART` con capacidades y ventas mensuales.
- Uso de datos PDF aun cuando el Excel mensual no esté disponible.
- Selector de semana PDF para consultar el histórico en los tableros.
- Estado de extracción y número de registros visibles en Histórico PDF.
- Reprocesamiento de PDF cargados con V53 al volver a seleccionarlos.
- Mensaje de fuente mensual corregido para no bloquear el módulo comercial.

## Validación de referencia

Con `AC IZT.pdf` se validaron 621 registros extraídos: 141 agregados comerciales
y 480 filas de rankings de modelos.
