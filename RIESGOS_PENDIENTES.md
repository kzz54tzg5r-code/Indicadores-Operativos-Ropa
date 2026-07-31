# Riesgos pendientes
1. Streamlit Community Cloud puede seguir limitado por memoria con libros Excel de 80 MB; el procesamiento por etapas debe mantenerse.
2. PostgreSQL requiere configurar conexión/secretos fuera del ZIP; V24 usa SQLite por defecto.
3. Las pruebas de integración con el Excel real, correo, OneDrive y usuarios concurrentes requieren infraestructura y datos que no se incluyen en el proyecto.
4. La capa visual heredada conserva complejidad histórica. La migración completa de cada pantalla debe hacerse por etapas después de validar paridad funcional.
5. Las capturas incluidas son referencias de tema V24, no evidencia de despliegue en Streamlit Cloud.
