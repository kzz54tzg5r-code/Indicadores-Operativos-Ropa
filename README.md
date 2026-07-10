# Indicadores Cambios y Muertos v10.28

Corrección de Resultados productividad 2:

- La hoja nueva puede venir sin encabezados.
- Se reconoce el formato mostrado:
  - B: Fecha
  - C: Tienda
  - D: Tabla
  - E: Nómina / colaborador
  - F: Actividad Realizada
  - G: Motivo
  - H: Número de piezas
  - I: Hora Inicio
  - J: Hora Fin
- Se detecta automáticamente la columna de fecha y se aplica el mapeo relativo.
- `Ubicado` alimenta Piezas Ubicadas.
- `Acondicionado` alimenta Piezas Acondicionadas.
- `Recolección de muertos` alimenta Recolectadas.
- Muertos conserva la regla estricta:
  Actividad = Recolección de muertos y Motivo = Muertos.
- `Ingreso` también se considera dentro de Recolectadas para la nueva fuente.

Actualización:
1. Sustituye los archivos del repositorio.
2. Reinicia Streamlit.
3. Borra el archivo persistido.
4. Carga nuevamente el Excel.
5. Presiona Procesar archivo.
6. Revisa Diagnóstico: debe indicar `Modo lectura: sin encabezados`.
