# V43 — alcance por reporte, pendientes semanales, nombres y ordenamiento

- Centro Ejecutivo: ranking comercial con todas las tiendas autorizadas; tabla operativa y KPI del proyecto mantienen solo las tiendas configuradas.
- Centro Ejecutivo: agrega tabla operativa mensual del proyecto antes de la gráfica operativa.
- Reporte Semanal: pendiente reinicia cada lunes; no se arrastra ni suma al ingreso de la semana.
- Reporte Semanal: ranking de recuperación usa todas las tiendas autorizadas.
- Reporte Mensual: elimina Pend. Ant. de la tabla; ranking de recuperación usa todas las tiendas autorizadas.
- Tablas: porcentajes, moneda y números se conservan como valores numéricos en AgGrid para ordenar correctamente (100% > 60% > 15%).
- Productividad: consulta histórica completa por defecto; limpia números de nómina, omite NaN y agrupa abreviaciones compatibles dentro de la misma tienda (por ejemplo Ivon/Ivonne cuando no hay ambigüedad).
- Recuperación: filtros de año y semana abren con todo el histórico seleccionado para evitar pantalla aparentemente vacía.
- Gráficas operativas: etiquetas reposicionadas; barras muestran valores internos y el ingreso se etiqueta por encima de la serie mayor para evitar encimamientos.
- Se conserva el resaltado tenue de las tiendas que pertenecen al proyecto.
