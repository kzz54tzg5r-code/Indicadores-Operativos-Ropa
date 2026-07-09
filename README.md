# Indicadores Cambios y Muertos v10.16

Correcciones:
- Se corrige KeyError: Fecha_txt en Diagnóstico.
- Se normaliza el comercial antes de guardar cache y antes de usarlo:
  Guadalajara Miravalle / Miravalle => Miravalle
  Guadalajara / Guadalajara Atemajac / Atemajac => Atemajac
- Se reagrupa después de homologar para que Dev Pzs se refleje en Miravalle/Atemajac.

Después de subir:
1. Reinicia app.
2. Borra archivo persistido.
3. Carga nuevamente Excel.
4. Procesar archivo activo.
