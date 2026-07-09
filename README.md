# Indicadores Cambios y Muertos v10.7

Corrección:
- Lector comercial reconstruido por bloques de fecha.
- Cada fecha lee Ventas Neta Pzs, Dev Pzs y Venta Neta $.
- Se genera tabla normalizada: Fecha | Tienda | Dev_Pzs | Vta_Pzs | Vta_Imp.
- Cache versionado v10.7.

Después de subir:
1. Reinicia la app.
2. Borra archivo persistido.
3. Carga nuevamente el Excel.
4. Presiona Procesar archivo activo.
