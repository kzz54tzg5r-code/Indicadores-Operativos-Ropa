# PS Operaciones Ropa V20.4

## Barra lateral
- PS Operaciones Ropa permanece fijo en la parte superior.
- Únicamente el listado de páginas se desplaza.
- Se agregó una barra de desplazamiento discreta al menú.

## Rendimiento
- Una actualización visual ya no invalida el caché de datos.
- Volver a cargar el mismo archivo conserva el procesamiento anterior.
- Se agregó validación SHA-256 del archivo.
- Se agregó Calamine, un lector de Excel en Rust, para acelerar las hojas comerciales.
- OpenPyXL permanece como respaldo automático.
- Al presionar procesar sobre un archivo sin cambios se reutiliza el caché.
