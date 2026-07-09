# Indicadores Cambios y Muertos v10.15

Correcciones:
- Fecha comercial normalizada: evita timestamps como 1781308800000.
- Homologación aplicada antes de agrupar:
  Guadalajara Miravalle / Miravalle => Miravalle
  Guadalajara / Guadalajara Atemajac / Atemajac => Atemajac
- Reagrupa después de homologar para que Miravalle y Atemajac sumen correctamente.
- Diagnóstico comercial muestra Fecha_txt YYYY-MM-DD.

Después de subir:
1. Reinicia app.
2. Borra archivo persistido.
3. Carga nuevamente Excel.
4. Procesar archivo activo.
