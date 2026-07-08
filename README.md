# Indicadores Cambios y Muertos v10.5

Corrección principal:
- Dev Pzs ahora detecta dinámicamente la fila de encabezados, usando:
  fila superior = fecha,
  fila de encabezado = Tienda / Dev Pzs.
- Esto corrige casos donde la fecha está a la derecha/izquierda del bloque y no quedaba amarrada a Dev Pzs.
- Cache versionado v10.5: después de subirlo hay que volver a presionar Procesar archivo activo.

Validación:
- En Diagnóstico se agrega validación de Dev Pzs por fecha/tienda.
- Si existe Ecatepec 28/06/2026, muestra el total detectado.
