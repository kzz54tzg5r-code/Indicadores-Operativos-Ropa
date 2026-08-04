# PS Operaciones Ropa V34

- La carga de Excel permanece únicamente en su módulo del menú.
- Todos los filtros de selección múltiple se muestran dentro de menús desplegables compactos.
- El OWNER hereda explícitamente todos los permisos de ADMIN, incluida la administración de usuarios y la carga de información.
- Todos los encabezados de tablas usan exclusivamente azul Price Shoes y texto/iconos blancos.
- Se agregó restauración automática del Excel desde almacenamiento persistente mediante el secreto `PS_DATA_SOURCE_URL`.

## Persistencia en Streamlit Cloud

El disco local de Streamlit Cloud se reemplaza al desplegar una nueva versión. Para conservar la base entre despliegues, configura en **Manage app → Settings → Secrets** una URL de descarga directa de OneDrive, SharePoint, S3 o Supabase:

```toml
PS_DATA_SOURCE_URL = "https://.../archivo.xlsx?download=1"
```

Cuando una instancia nueva no encuentre `data/uploads/base_activa.xlsx`, descargará automáticamente la fuente configurada. Después debe procesarse si el caché no está disponible.
