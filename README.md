# Indicadores Cambios y Muertos v10.27

Corrección principal:
- La aplicación ya no limita la operación a la última fecha de las hojas comerciales.
- Se conserva la información de `Resultados productividad 2` desde el 29/06/2026.
- Los registros del 09/07/2026 ahora alimentan:
  - Recolectadas
  - Habilitadas
  - Ubicadas
  - Muertos
  - Cajas
  - Probador
  - Indicadores diarios, semanales y mensuales

Causa del error:
La versión anterior tomaba el 28/06/2026 como fecha máxima porque era la última
fecha comercial. Por eso los registros operativos de julio se filtraban y aparecían
como cero.

Para actualizar:
1. Sustituye los archivos del repositorio.
2. Reinicia Streamlit.
3. Borra el archivo persistido.
4. Carga nuevamente el Excel con `Resultados productividad 2`.
5. Procesa nuevamente el archivo.
