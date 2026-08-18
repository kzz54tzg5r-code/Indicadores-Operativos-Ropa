# Cambios V55 · Análisis Comercial sólo PDF

## Alcance

El módulo comercial utiliza exclusivamente los reportes AC semanales en PDF. Los archivos mensuales de ventas y capacidades quedan fuera de los cálculos y de la interfaz hasta definir su siguiente etapa.

## Nuevas vistas

- **Resumen:** IDs, curva, piso, bodega, existencia, VPD, DDI y DDC; evolución semanal, sección, ubicación y tienda.
- **Tiendas:** ranking, rotación, cobertura, concentración en bodega y score operativo.
- **Inventario:** rangos de cobertura, proyección simple al ritmo VPD y modelos destacados con riesgo.
- **Secciones:** sección, categoría, rubro, catálogo, estatus y tipo de producto.
- **Ubicaciones:** Doblado, Colgado, Jeans y Lencería con productividad del espacio.
- **Marcas:** Top 40 General y Nacional por utilidad, VPD, existencia, cobertura y posiciones.
- **Modelos:** rankings PDF de Utilidad, Sugerido/VPD, Baja rotación e Inversión.
- **Oportunidades:** agotamiento, sobrecobertura, bodega, catálogo de salida, lentos y transferencias.
- **Histórico:** cobertura de los 17 PDF y evolución por semana.

## Carga y persistencia

- Un solo cargador para hasta 17 PDF por corte.
- Extracción paralela de cuatro archivos a la vez.
- Reconocimiento de tienda por nombre del archivo y contenido.
- Snapshot estructurado con versión de parser para evitar reprocesar en cada navegación.
- Respaldo y restauración del histórico PDF.

## Criterios de integridad

- No se muestran venta monetaria, utilidad monetaria, inversión total de compañía ni piezas vendidas porque esos datos no están completos en los PDF.
- `% Utilidad` se identifica como porcentaje publicado, no como monto.
- La inversión sólo aparece en el ranking de inversión impreso en el PDF.
- El detalle de modelos se declara como Top 40 publicado y no como universo completo.
- Lencería se identifica por rubro y no se suma como una ubicación física excluyente.
