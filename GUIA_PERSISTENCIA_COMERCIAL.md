# Persistencia del histórico comercial

Los archivos escritos directamente por una aplicación de Streamlit Cloud pueden desaparecer cuando la aplicación reinicia o se vuelve a desplegar. El módulo comercial incluye sincronización con un bucket **privado** de Supabase Storage para que los 17 PDF semanales, ventas, capacidades y métricas procesadas sobrevivan esos reinicios.

## Configuración única

1. Crea un proyecto en Supabase.
2. En **Storage**, crea un bucket privado llamado `ps-operaciones-private`.
3. En Supabase, copia la URL del proyecto y la clave `service_role`.
4. En Streamlit Cloud abre **Manage app > Settings > Secrets** y agrega:

```toml
PS_COMMERCIAL_SUPABASE_URL = "https://TU-PROYECTO.supabase.co"
PS_COMMERCIAL_SUPABASE_KEY = "TU_SERVICE_ROLE_KEY"
PS_COMMERCIAL_SUPABASE_BUCKET = "ps-operaciones-private"
PS_COMMERCIAL_SUPABASE_PREFIX = "commercial"
```

5. Guarda los secretos y reinicia la aplicación.

La clave debe permanecer únicamente en los secretos de Streamlit. Nunca la agregues al repositorio ni a un archivo que se suba a GitHub.

## Primera carga después de instalar esta versión

La versión anterior guardó los PDF sólo en el disco temporal y no es posible recuperarlos después del reinicio. Por eso se deben volver a cargar una sola vez los 17 PDF del corte actual desde **Carga comercial**. Cuando la pantalla muestre **Histórico protegido**, cada archivo nuevo se guardará también en el bucket privado.

## Qué se restaura automáticamente

- Manifiesto de archivos y cobertura de las 17 tiendas.
- Métricas normalizadas de cada PDF para Resumen e Histórico.
- Archivos mensuales de ventas.
- Archivos de capacidades y existencias.
- Acciones comerciales guardadas.

Los PDF originales permanecen en el bucket. Al iniciar, la aplicación descarga sólo los datos normalizados y los archivos tabulares necesarios; así evita descargar nuevamente todos los PDF históricos.
