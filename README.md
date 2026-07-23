# Indicadores Cambios y Muertos v13.0

Cambios comerciales:
- Se reemplazó la referencia SKU por ID.
- El lector de hojas mensuales detecta y conserva la columna ID.
- Conversión calculada por ID, tienda y semana ISO.
- Se eliminó el cálculo inestable que producía el error de `.clip()`.
- Recuperación Económica utiliza Venta Neta en $, no Costo Dev.
- Se muestran Venta Neta $, Venta Neta Recuperada $, Pendiente $ y Recuperación %.
- Para aplicar la nueva agrupación por ID es necesario volver a cargar y procesar el Excel.
