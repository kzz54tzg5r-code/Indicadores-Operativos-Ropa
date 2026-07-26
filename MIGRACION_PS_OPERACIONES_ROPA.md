# Migración inicial a PS Operaciones Ropa — v0.1.0

Esta versión parte del proyecto existente **Indicadores Operativos Ropa** y conserva su funcionamiento actual en Streamlit.

## Cambios realizados

- Nombre visible actualizado a **PS Operaciones Ropa**.
- Subtítulo institucional: **Plataforma Integral de Gestión Operativa**.
- Se conservaron el logo y los recursos visuales de Price Shoes.
- Encabezados de los PDF actualizados al nuevo nombre.
- Archivos `__pycache__` y `.pyc` eliminados del entregable.
- Configuración institucional agregada en `config/proyecto.json`.

## Funcionalidad conservada

- Dashboard y reportes diario, semanal y mensual.
- Conversión y recuperación económica.
- Cálculo FIFO por tienda, ID/SKU, color, año ISO y semana ISO.
- Productividad, recorridos, rankings y macro.
- Exportaciones PDF, Excel y CSV existentes.
- Carga y administración de archivos.

## Siguiente incremento recomendado — v0.2.0

1. Implementar perfiles `OWNER`, `ADMIN`, `DIRECTOR`, `REGIONAL`, `TIENDA`, `SUPERVISOR` y `CONSULTA`.
2. Asignar alcance por compañía, región y tienda.
3. Personalizar el Centro Ejecutivo según el usuario.
4. Incorporar Centro de Control con estados Activo, Solo consulta, Mantenimiento y Suspendido.
5. Sustituir credenciales de demostración y contraseñas incrustadas por secretos seguros.
6. Estandarizar todos los PDF con filtros, usuario, alcance, fecha y nombre de archivo institucional.
