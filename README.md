# Indicadores Cambios y Muertos v10.25

Corrección:
- Se corrigió `available_iso_weeks()`.
- Pandas cambiaba los nombres `_iso_year` y `_iso_week` al usar `itertuples()`.
- Ahora se usan columnas sin guion bajo y `itertuples(name=None)`.

Error corregido:
`AttributeError` en `r._iso_year`.

Para actualizar:
1. Sustituye los archivos del repositorio.
2. Reinicia la aplicación en Streamlit Cloud.
3. No es necesario reprocesar el Excel.
