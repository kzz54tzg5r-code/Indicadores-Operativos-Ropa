# Indicadores Cambios y Muertos v10.0

Versión reestructurada para rendimiento:
- No procesa el Excel al iniciar.
- El administrador carga el Excel y luego presiona "Procesar archivo activo".
- Guarda cache en Parquet para que las siguientes cargas sean rápidas.
- Lee la hoja "Resultados productividad" y las hojas mensuales por openpyxl read_only.
- Pestañas con cálculo bajo demanda.
- Tablas AgGrid con encabezado azul y letras blancas.
- Diseño Price Shoes con línea rosa superior.
- Usuarios persistentes en SQLite.

Usuario inicial:
- admin
- admin123
