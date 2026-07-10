# Indicadores Cambios y Muertos v10.29

Corrección:
- Se sustituyó la lectura de Resultados productividad 2 por lectura directa con openpyxl.
- Se detecta la fila real de encabezados.
- Reconoce exactamente:
  Occurrence, Fecha, Ubicación, Tabla, Nómina, Actividad Realizada,
  Ingreso al area de acondicionado, Número de piezas, Hora Inicio y Hora Fin.
- La información del 09/07/2026 debe alimentar Acondicionado, Ubicado, Muertos,
  Cajas, Probador y Recolectadas.

Actualización obligatoria:
1. Sustituye los archivos del repositorio.
2. Reinicia Streamlit.
3. Borra el archivo persistido.
4. Carga nuevamente el Excel.
5. Presiona Procesar archivo.
6. En Diagnóstico, Resultados productividad 2 debe mostrar Estado = OK,
   la fila de encabezado y el número de filas leídas.
