# Indicadores Cambios y Muertos v10.2

Correcciones:
- Dashboard Ejecutivo ahora muestra tarjetas de últimas 4 semanas como el boceto.
- Pendiente anterior corregido: sólo toma lo pendiente por ubicar del día anterior al periodo, no todo el histórico.
- Base del periodo: ingresos del periodo + pendiente anterior.
- Parser mensual lee Dev Pzs desde la fila 3 para no perder datos visibles del archivo.
- Cache versionado v10.2: obliga a reprocesar el Excel para evitar usar datos viejos.
- Diagnóstico incluye validación Dev Pzs por fecha y tienda.

Después de subir esta versión, presiona "Procesar archivo activo" nuevamente.
