# PS Operaciones Ropa V20.6

## Estabilidad de procesamiento
- El Excel se procesa en un hilo independiente de la sesión del navegador.
- Si Chrome o Streamlit reconectan la sesión, el procesamiento continúa.
- El avance se guarda en `config/estado_proceso.json`.
- Se puede navegar a otra pestaña mientras procesa.
- Los errores completos se muestran en un expander técnico.

## Sesión
- El token propio cambió de `?session=` a `?ps_auth=`.
- Los enlaces antiguos se migran automáticamente.
- Esto evita confundir el token de autenticación de la aplicación con la
  administración interna de sesiones de Streamlit.

## Rendimiento
- Operación, Plantilla y hojas comerciales usan Calamine cuando está disponible.
- Para archivos grandes se evita el respaldo OpenPyXL de varias horas.
