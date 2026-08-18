# Cambios V54

- El Resumen Comercial se reconstruyó conforme al boceto aprobado: filtro semanal, ocho KPI, alerta, tendencia, participación por sección, ubicación y ranking compacto de tiendas.
- Los datos de los PDF del corte seleccionado ahora tienen prioridad para existencia, VPD y DDI; ventas, inversión y utilidad se complementan desde los Excel.
- Se agregó persistencia opcional en un bucket privado de Supabase Storage.
- Cada PDF conserva un snapshot normalizado para restaurar el histórico sin descargar y reprocesar todos los originales.
- La carga muestra claramente si el histórico está protegido o continúa sólo en almacenamiento temporal.
- El encabezado informa cobertura del último corte y fecha de actualización.
