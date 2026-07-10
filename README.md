# Indicadores Cambios y Muertos v10.26

Cambios principales:

1. Nueva hoja operativa
- Lee `Resultados productividad`.
- Lee y concatena `Resultados productividad 2`.
- La segunda hoja se considera a partir del 29/06/2026.
- También reconoce temporalmente el alias `Resultados por Checklist`.
- Mapea:
  - Ubicación -> Tienda
  - Actividad Realizada -> Actividad
  - Ingreso al area de acondicionado -> Motivo
  - Número de piezas -> Piezas
  - Nómina -> Nombre

2. PDF semanal y mensual
- Incluyen tarjetas KPI.
- Incluyen tabla.
- Incluyen gráfico combinado.
- El porcentaje de ubicación se muestra:
  - rojo cuando es menor a 75%;
  - verde cuando es igual o mayor a 90%;
  - negro entre 75% y 89.9%.

Después de actualizar:
1. Sustituye los archivos en GitHub.
2. Reinicia la aplicación.
3. Borra el archivo persistido.
4. Carga el Excel que ya contenga la pestaña `Resultados productividad 2`.
5. Procesa nuevamente el archivo.
