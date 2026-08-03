# PS Operaciones Ropa V27 — Avance objetivo

## Cambios visibles
- Layout maestro autoritativo para evitar que estilos heredados deformen el encabezado, sidebar o contenido.
- Encabezado compacto y proporcional con logo, nombre, usuario y perfil.
- Sidebar corporativo con iconos, navegación completa y control nativo para ocultar/mostrar.
- Centro Ejecutivo con seis tarjetas KPI responsive, sin columnas comprimidas.
- Alertas compactas antes de gráficas y tablas.
- Macro por tiendas con ajuste automático de columnas y sin desplazamiento horizontal.
- Mensaje de fuente pendiente compacto y acceso directo a Carga de Excel.
- Reglas responsive para escritorio, tableta y móvil.

## Se conserva
- Cálculos de operación, productividad, recorridos y recuperación.
- FIFO por tienda, año ISO, semana ISO, ID/SKU y color.
- Roles, permisos, PDF, Excel, diagnóstico y administración existentes.

## Limitación conocida
El Excel cargado sigue alojado en el almacenamiento temporal de Streamlit Cloud. Para persistencia después de redespliegues se requiere conectar OneDrive, SharePoint, S3 o Supabase Storage con credenciales del propietario.
