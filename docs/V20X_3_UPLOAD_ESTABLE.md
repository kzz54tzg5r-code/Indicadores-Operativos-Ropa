# PS Operaciones Ropa V20X.3

## Corrección de ClientDisconnect

El error ocurría porque el navegador conservaba un archivo de 80 MB dentro
del widget de carga. Al cambiar de pestaña, Streamlit cancelaba la petición
multipart y Starlette registraba `ClientDisconnect`.

## Cambio aplicado

- El selector se desmonta después de guardar el archivo.
- Cuando ya existe una fuente activa, el selector no se muestra.
- Para cambiar el Excel se debe presionar `Seleccionar otro archivo`.
- Se añadió una clave dinámica al uploader para limpiar su estado.
- Cambiar de pestaña ya no intenta volver a transmitir el archivo.
- Se conserva el avance del procesamiento por etapas.
