# V20X.3.6 Consulta Selectiva

- Operación Diaria: último día disponible.
- Centro Ejecutivo y Semanal: últimas cuatro semanas.
- Mensual: últimos tres meses.
- Productividad: últimos 30 días.
- Recorridos: semana más reciente.
- Recuperación: últimas 12 semanas.
- Se leen los Parquet con filtros de fecha antes de convertirlos a DataFrame.
- No se cargan simultáneamente los históricos completos de operación y comercial.
