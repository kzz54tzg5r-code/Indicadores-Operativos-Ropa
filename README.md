# Indicadores Cambios y Muertos v10.14.1

Corrección:
- Soluciona ArrowTypeError en el diagnóstico técnico.
- Convierte columnas mixtas del diagnóstico a texto antes de guardar parquet.
- Mantiene el diagnóstico Dev Pzs para revisar columna, valor crudo y valor numérico.

Después de subir:
1. Reinicia la app.
2. Borra archivo persistido.
3. Carga nuevamente el Excel.
4. Procesar archivo activo.
