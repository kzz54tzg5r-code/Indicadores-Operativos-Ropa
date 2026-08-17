# V53 · Ventas y Análisis Comercial

Esta versión agrega un segundo proyecto activo al menú principal sin retirar
los módulos de Muertos y Cambios.

## Pestañas incluidas

1. Resumen: indicadores globales, tendencia, participación y desempeño.
2. Tiendas: comparativo y score comercial para las 17 tiendas.
3. Ubicaciones: análisis de Doblado, Colgado, Jeans y Lencería por sección.
4. Modelos: top 20 de campeones, lentos y modelos en riesgo.
5. Inventario: cobertura, agotamientos, exceso e inversión detenida.
6. Oportunidades: resurtidos, transferencias y revisiones de precio/ubicación.
7. Pronóstico: escenarios de Sugerido/VPD y Utilidad a 4, 8 o 12 semanas.
8. Histórico: evolución semanal y cobertura de PDF por tienda.
9. Carga comercial: pantalla administrativa para subir ventas, capacidades y
   hasta 17 PDF por semana.

## Fuentes y persistencia

- `data/commercial/ventas`: libros mensuales de ventas.
- `data/commercial/capacidades`: capacidades y existencias por tienda/modelo.
- `data/commercial/pdfs/<semana>`: PDF semanales; nunca se reemplazan al
  cargar una semana posterior.
- `data/commercial/manifest.json`: trazabilidad, validación y detección de
  duplicados por contenido.

La pantalla Carga comercial permite descargar un respaldo ZIP del histórico y
restaurarlo sin borrar los archivos que ya existen.

## Archivos de ejemplo incluidos

- Capacidades: `capacidades_24.04.26.xls` (Olivar).
- PDF: `AC_IZT.pdf` (Iztapalapa, semana 14 de 2024).

Estos archivos permiten abrir el módulo con información desde el primer inicio
y pueden sustituirse o complementarse desde Carga comercial.
