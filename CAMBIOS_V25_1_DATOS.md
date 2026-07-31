# V25.1 — Corrección de datos en reportes

- Se separó el horizonte temporal de operación y comercial.
- Se agregó lectura de respaldo del caché completo cuando una ventana optimizada queda vacía.
- Se añadió un marcador visible de versión para comprobar el despliegue correcto.
- La meta predeterminada de recuperación económica se ajustó a 100%.

## Verificación posterior a la carga

En la parte inferior del reporte debe aparecer: `PS Operaciones Ropa · V25.1 · Motor de datos corregido`.
Si no aparece, Streamlit sigue ejecutando archivos anteriores o el ZIP se subió dentro de una carpeta anidada.
