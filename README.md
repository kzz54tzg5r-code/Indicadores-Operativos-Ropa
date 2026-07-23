# Indicadores Cambios y Muertos v12.7

Corrección aplicada:
- Se definió correctamente `FILE_HISTORY`.
- El historial se guarda en `data/file_history.json`.
- Si el historial no existe o está dañado, la aplicación continúa normalmente.
- Un error al escribir el historial ya no bloquea la carga ni el procesamiento del Excel.
- Se mantienen únicamente los permisos Administrador y Consulta.
