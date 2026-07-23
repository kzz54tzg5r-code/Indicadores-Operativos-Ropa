# Indicadores Cambios y Muertos v13.1

Optimización de carga y procesamiento:
- La carga se divide en dos pasos: Guardar y Procesar.
- Guardar el archivo ya no espera a que termine todo el procesamiento.
- El lector comercial ya no convierte cada hoja completa en una lista.
- Solo lee las columnas necesarias: Tienda, ID, Color, Dev Pzs, Venta Pzs y Venta Neta $.
- Se redujo la cantidad de registros de diagnóstico de muestra.
- Se eliminaron normalizaciones duplicadas.
- Se mantiene el cálculo por ID y Venta Neta en $.

Para un archivo de aproximadamente 80 MB, la subida seguirá dependiendo de la velocidad
de internet, pero el procesamiento en el servidor debe consumir menos memoria y terminar
más rápido.
