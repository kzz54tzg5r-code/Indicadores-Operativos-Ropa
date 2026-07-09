# Indicadores Cambios y Muertos v10.17

Corrección:
- Evita invertir mes/día en filtros de Por Día.
- YYYY/MM/DD se interpreta como año-mes-día.
- DD/MM/YYYY se interpreta como día-mes-año.
- Reforzada comparación de fechas entre Operación y Comercial.
- Reforzada normalización de fecha comercial usando parse_date.

Después de subir:
1. Reinicia app.
2. Borra archivo persistido.
3. Carga nuevamente Excel.
4. Procesar archivo activo.
5. Verifica Por Día con 2026/06/28.
