# Indicadores Cambios y Muertos v10.24

Corrección:
- Se escaparon correctamente las llaves del CSS dentro del f-string de `apply_styles()`.
- Se elimina el error:
  `NameError: position: relative !important;`

Mantiene:
- Semanas válidas hasta la última fecha real cargada.
- PDF en las pestañas de indicadores.
- Barra azul de extremo a extremo.
- Pestaña activa en blanco intenso y línea rosa.

Para actualizar:
1. Sustituye los archivos del repositorio.
2. Reinicia la aplicación desde Streamlit Cloud.
3. No es necesario reprocesar el Excel.
