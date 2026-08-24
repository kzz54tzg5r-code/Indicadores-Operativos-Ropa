# V36
- Menús múltiples estables, tiendas del proyecto resaltadas y recorridos corregidos.

# V34
- Persistencia remota opcional, filtros compactos, permisos OWNER y tablas azules.

# V32

- Navegación interna persistente corregida.
- Layout a ancho completo.
- Encabezados blancos en hero y tablas.
- Eliminación de texto Portafolio.

# V27.0.0 — 2026-08-03
- Layout maestro estable y responsive.
- Navegación lateral con iconos.
- Encabezado proporcional.
- KPIs ejecutivos responsive.
- Alertas compactas arriba del contenido.
- Tabla Macro ajustada al ancho.
- Acceso directo a carga cuando falta la fuente.

# CHANGELOG — PS Operaciones Ropa V24 Producción

## 24.0.0 — 30/07/2026
- Entrada `app.py` reducida a bootstrap y capa de compatibilidad.
- Configuración central de identidad, rutas, colores, metas y estados.
- Control de roles OWNER, ADMIN, DIRECTOR, REGIONAL, TIENDA, SUPERVISOR y CONSULTA.
- Filtrado de alcance COMPANY, REGION, STORE y TEAM antes de cálculos/exportaciones.
- Servicios unificados de operación, productividad, conversión, recuperación, recorridos, alertas e inteligencia.
- Fórmula semanal oficial de conversión por Tienda + Año ISO + Semana ISO + ID/SKU + Color.
- Porcentajes consolidados por suma de numeradores / suma de denominadores.
- Persistencia SQLite para usuarios, auditoría, metas, descargas y estado del sistema.
- Contraseñas Argon2id y protección de OWNER.
- Exportadores PDF/Excel reutilizables y registro de descargas.
- Eliminación de alertas, históricos e inteligencia con datos ficticios.
- Ajuste responsive del layout y del encabezado de usuario.
- Pruebas automatizadas de fórmulas, permisos y productividad.

## V24.0.1 — Corrección de arranque en Streamlit Cloud
- Se agrega explícitamente la raíz del repositorio a `sys.path` antes de importar módulos locales.
- Se valida que existan `core/bootstrap.py`, `core/settings.py` y `legacy_app.py`.
- Se reemplaza el error ambiguo `ModuleNotFoundError` por un mensaje claro cuando la carga a GitHub está incompleta.

## 24.0.2 — 2026-07-31
- Corregida la compatibilidad entre `legacy_app.py` y `core/settings.py`.
- Agregadas constantes heredadas requeridas por la aplicación: colores, rutas de metadatos, historial, sesiones, estados, etiquetas de roles y archivos de procesamiento.
- Corregido el `ImportError` al importar nombres desde `core.settings`.
- Validada la existencia de las 30 constantes importadas por `legacy_app.py`.

## V25.0.0 — Reportes visuales y ecuaciones ejecutivas
- Rediseño corporativo responsive.
- Centro Ejecutivo integral con PS Score.
- Reportes diario, semanal y mensual ampliados.
- Productividad y recorridos corregidos.
- PDF y Excel en reportes principales.
- 15 pruebas aprobadas.

## V25.3
- Layout principal, menú lateral, alertas y tablas ajustadas.

## V37
- Centro Ejecutivo mensual con selector de mes.
- Tarjetas de las últimas cuatro semanas con indicadores comerciales completos.
- Macro por tiendas filtrable por semana ISO.
- Reporte semanal: tabla antes de gráfica operativa y tendencia sin series vacías.
- Ajustes de layout en gráficas mensuales y semanales.

## V75 · Acordeón + desktop
- Nueva pestaña Acordeón Comercial.
- Carga de ventas mensual con estado acumulado/cierre.
- Render comercial directo para corregir panel central blanco en escritorio.
- Logo HTML sin control de ampliación de imagen.
