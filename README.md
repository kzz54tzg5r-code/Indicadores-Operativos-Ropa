# v9.5 Fix Dev Pzs mensual

Corrección principal:
- La función que lee Dev Pzs de hojas mensuales ya existía, pero no se estaba anexando al dataframe comercial.
- Ahora load_normalized une co + monthly_dev_by_date(sheets).
- La pestaña Por Día ya debe tomar Ecatepec 28/06/2026 desde Junio 26 -> columna Dev Pzs.
- Se agregó diagnóstico en la leyenda: Dev Pzs mensual detectado.
