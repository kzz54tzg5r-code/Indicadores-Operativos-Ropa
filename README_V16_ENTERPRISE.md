# Indicadores Cambios y Muertos — v16 Enterprise

## Cambios integrados

### Estabilidad y sesión
- Sesión persistente de 8 horas con renovación por actividad.
- Recuperación de sesión después de rerun, refresco o reinicio del proceso.
- Archivo activo y caché permanente.
- Sin `st.dialog`.
- Administración como página completa.
- API actualizada de `use_container_width` a `width`.

### Conversión y recuperación
- Llave: Tienda + ID/SKU + Color + Año ISO + Semana ISO.
- Asignación FIFO.
- Una venta únicamente recupera una devolución con fecha igual o posterior.
- Las semanas quedan cerradas; no hay recuperación retroactiva.
- Precio unitario neto = SUM(Venta Neta $) / SUM(Ventas Netas Pzs).
- Valor de la Devolución a Precio Neto.
- Recuperación en piezas y pesos.
- Porcentajes ponderados y limitados a 100%.
- Pendientes nunca negativos.

### Interfaz financiera
- Tarjetas ejecutivas.
- Macro consolidado por tienda.
- Ranking independiente en piezas y pesos.
- Vista comparativa.
- Tres gráficas ejecutivas.
- Detalle General por ID/SKU.
- Filtros por año, semana, tienda, ID/descripción, color y estado.
- Exportación CSV y Excel.
- Diagnóstico descargable.

### Pruebas
Se validó que:
- Piezas Recuperadas <= Dev Pzs.
- Recuperación $ <= Valor Devolución.
- Los porcentajes no superan 100%.
- Las ventas no se reutilizan entre semanas.
