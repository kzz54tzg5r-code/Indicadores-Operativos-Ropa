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
