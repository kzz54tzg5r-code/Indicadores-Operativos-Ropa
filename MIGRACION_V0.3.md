# Migración a PS Operaciones Ropa v0.3

## Objetivo
Incorporar la primera experiencia ejecutiva personalizada y reforzar el alcance territorial.

## Cambios
1. El antiguo **Resumen** se denomina **Centro Ejecutivo**.
2. El encabezado cambia según OWNER, ADMIN, DIRECTOR, REGIONAL, TIENDA, SUPERVISOR o CONSULTA.
3. Los KPIs de recuperación se calculan únicamente con la información autorizada para la sesión.
4. Los selectores semanales, mensuales y de productividad muestran solo tiendas autorizadas.
5. El PDF del Centro Ejecutivo incluye perfil, alcance, fecha y datos filtrados.
6. En estado READ_ONLY se deshabilitan carga, procesamiento, reproceso y eliminación del archivo activo.

## Validación recomendada
- Crear un usuario TIENDA con `scope_type=STORE` y `scope_value=Toluca`.
- Confirmar que no aparezcan otras tiendas en Centro Ejecutivo ni filtros.
- Cambiar el sistema a READ_ONLY y comprobar que la administración de archivos quede bloqueada.
