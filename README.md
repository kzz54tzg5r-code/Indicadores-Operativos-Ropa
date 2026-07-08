# Indicadores Cambios y Muertos v10.4

Correcciones:
- Se optimizó la lectura de hojas mensuales para que no se quede cargando.
- Ya no usa ws.cell dentro de ciclos grandes; ahora usa iter_rows(values_only=True).
- Dev Pzs se agrupa por Hoja + Fecha + Tienda para reducir datos y acelerar cache.
- Se corrigieron warnings de fechas ISO con dayfirst.
- Cache versionado v10.4: debes reprocesar el archivo activo.

Después de subir app.py y requirements.txt:
1. Reinicia la app en Streamlit Cloud.
2. Inicia sesión.
3. Presiona “Procesar archivo activo”.
