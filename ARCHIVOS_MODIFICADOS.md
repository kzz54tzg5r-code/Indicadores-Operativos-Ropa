# Archivos modificados y creados
- app.py (bootstrap de producción)
- legacy_app.py (compatibilidad V21, branding, responsive y eliminación de datos demo)
- core/settings.py, bootstrap.py, permissions.py, database.py, audit.py, system_state.py
- services/metrics.py, conversion.py, productivity.py, recorridos.py, alerts.py, intelligence.py, downloads.py, pdf_service.py, excel_service.py
- pages_app/*.py (módulos de presentación preparados)
- tests/*.py
- requirements.txt
- CHANGELOG.md, AUDITORIA_INICIAL.md, RESULTADOS_PRUEBAS.md, RIESGOS_PENDIENTES.md, MIGRACION_V24.md, GUIA_GITHUB_STREAMLIT.md

## V75 / ORION_MOBILE_V8
- commercial/config.py: nueva ruta Acordeón Comercial y orden de navegación.
- commercial/ui.py: logo HTML sin visor, carga mensual de ventas, corte acumulado/cierre, carga selectiva y navegación móvil de 7 accesos.
- commercial/pdf_pages.py: nueva vista Acordeón Comercial con estructura del formato de referencia.
- commercial/parsers.py: lectura de fechas de ventas robusta para ISO y dd/mm/aaaa.
- legacy_app.py: render directo del módulo comercial para corregir la pantalla central en blanco en escritorio.
- CAMBIOS_V75_ACORDEON_DESKTOP.md: detalle funcional de la versión.
