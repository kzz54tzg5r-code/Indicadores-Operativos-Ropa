# PS Operaciones Ropa V20X.3.5

## Corrección de lentitud al cambiar de pestaña

La aplicación cargaba los archivos completos de operación y comercial antes
de saber qué página se iba a mostrar. Por eso entrar a `Carga de Excel`
también abría toda la base procesada.

## Cambios

- Carga diferida por página.
- `Carga de Excel`, Administración, Perfil, Centro de Control y Configuración
  abren sin leer los Parquet grandes.
- Diagnóstico lee únicamente su archivo de diagnóstico.
- Los reportes siguen cargando la información cuando realmente la necesitan.
- Se conserva el procesamiento por etapas y el esquema Low Memory.
