# PS Operaciones Ropa v0.2 — Perfiles, alcances y Centro de Control

## Cambios incluidos

- Perfiles: OWNER, ADMIN, DIRECTOR, REGIONAL, TIENDA, SUPERVISOR y CONSULTA.
- Alcance territorial por compañía, región, tienda o equipo.
- Filtro obligatorio de datos por tienda antes de renderizar reportes, tablas, gráficas y PDFs.
- Centro de Control exclusivo para OWNER.
- Estados del sistema: Activo, Solo consulta, Mantenimiento y Suspendido.
- Auditoría de cambios de estado y administración de usuarios.
- Administración de usuarios con correo, perfil y asignación territorial.
- Protección del perfil OWNER contra eliminación desde la interfaz.
- Metadatos de usuario, alcance, fecha y hora incorporados en los PDFs genéricos.
- Compatibilidad con la base SQLite existente; la migración de columnas se ejecuta automáticamente.

## Primer acceso

El usuario histórico `admin` se conserva y se migra a OWNER.

- Usuario: `admin`
- Contraseña inicial heredada: `admin123`

Cambia esta contraseña antes de usar la plataforma con información real.

## Ejemplos de asignación

- Director: perfil `DIRECTOR`, alcance `COMPANY`.
- Gerente Toluca: perfil `TIENDA`, alcance `STORE`, asignación `Toluca`.
- Regional Centro: perfil `REGIONAL`, alcance `REGION`; mientras se integra el catálogo de regiones, usa en Asignación una lista de tiendas separadas por comas.

## Consideraciones

La v0.2 aplica seguridad territorial dentro de la aplicación Streamlit. Para una etapa empresarial posterior, la validación deberá migrarse también a FastAPI/PostgreSQL para que la seguridad no dependa del proceso de interfaz.
