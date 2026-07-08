# Indicadores Cambios y Muertos v10.6

Corrección principal:
- El lector de Dev Pzs ahora usa directamente la estructura real del archivo:
  Fila 1 = Fecha
  Fila 2 = Tienda / Dev Pzs
  Datos desde fila 3
- Se agregó canon_store más agresivo para ECATEPEC, VALLEJO, etc. en mayúsculas.
- Dev Pzs se agrupa por Hoja + Fecha + Tienda.
- Cache versionado v10.6.

Después de subirlo:
1. Reinicia app.
2. Presiona Borrar archivo persistido si aparece.
3. Carga el Excel.
4. Presiona Procesar archivo activo.
5. Revisa Diagnóstico: debe mostrar Columnas Dev, Valores Dev y Dev Pzs > 0.
