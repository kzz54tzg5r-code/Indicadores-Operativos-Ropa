# Indicadores Cambios y Muertos v10.14

Cambio:
- Se agrega diagnóstico técnico para Dev Pzs.
- Muestra columnas detectadas por fecha:
  Col Ventas Pzs, Col Dev Pzs, Col Venta $
- Muestra filas leídas con:
  Tienda cruda, Tienda homologada, Col Dev, Dev crudo, Dev num.
- Sirve para validar casos como Miravalle / Guadalajara Miravalle.

Después de subir:
1. Borra archivo persistido.
2. Carga nuevamente el Excel.
3. Procesar archivo activo.
4. Entra a Diagnóstico y revisa:
   - Columnas detectadas
   - Muestra lectura
