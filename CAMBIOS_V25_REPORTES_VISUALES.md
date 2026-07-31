# PS Operaciones Ropa V25 — Reportes y diseño ejecutivo

## Cambios visuales
- Sistema visual corporativo renovado con azul Price Shoes, acento rosa, tarjetas blancas, sombras ligeras y distribución adaptable.
- Nuevo grid de KPI responsive para computadora, tableta y móvil.
- Gráficas, tablas, pestañas y botones de descarga homologados.
- Centro Ejecutivo reorganizado para mostrar operación, conversión, recuperación económica, productividad, recorridos y PS Score.

## Cálculos incorporados o estandarizados
- `% Acondicionado = Acondicionado / Ingresos × 100`.
- `% Ubicado / Ingresos = Ubicado / Ingresos × 100`.
- `% Ubicado / Acondicionado = Ubicado / Acondicionado × 100`.
- Pendientes limitados a cero como mínimo.
- Productividad por colaborador y día trabajado, con meta acumulada de 784 piezas.
- Recorridos con meta semanal de 47 por tienda.
- Conversión y recuperación económica cerradas por tienda, año ISO, semana ISO, ID/SKU y color.
- Consolidados calculados como suma de numeradores / suma de denominadores, no como promedio de porcentajes.
- PS Score con pesos 30/25/20/15/10.

## Reportes mejorados
- Centro Ejecutivo: KPIs integrales, ranking, alertas, PDF y Excel.
- Operación Diaria: filtros por fecha y tienda, dos gráficas, PDF y Excel.
- Reporte Semanal: comparativo anterior, tendencia de cuatro semanas, productividad, recorridos, recuperación, PDF y Excel.
- Reporte Mensual: consolidado semanal cerrado, tendencia de tres meses, heatmap, PDF y Excel.
- Productividad: top 3, bottom 3, meta acumulada, faltante, PDF y Excel.
- Recorridos: ranking y semáforo por tienda, PDF y Excel.
- Detalle por tienda y colaborador: vista integral y exportaciones.

## Validación
- `app.py` y `legacy_app.py` compilan correctamente.
- 15 pruebas automatizadas aprobadas.
- Se añadió `tests/conftest.py` para que pytest resuelva correctamente los paquetes locales.

## Nota de ejecución
El entorno de validación no incluye el paquete Streamlit instalado, por lo que no fue posible levantar el servidor gráfico dentro del contenedor. La validación realizada incluye sintaxis y pruebas unitarias. Streamlit Cloud instalará las dependencias desde `requirements.txt`.
