# PS Operaciones Ropa v0.4

## Cambios principales

- Configuración centralizada en `core/settings.py`.
- Contraseñas nuevas protegidas con Argon2id.
- Compatibilidad temporal con hashes SHA-256 heredados y actualización automática al iniciar sesión.
- Cuenta propietaria inicial `JDA`, alcance Compañía y perfil `OWNER`.
- Desactivación automática del usuario de demostración `admin`.
- Registro del último acceso del usuario.
- Identidad del login actualizada a **PS Operaciones Ropa**.
- Eliminación de credenciales en texto plano del archivo `config/usuarios.json`.
- Versión central del sistema: `0.4.0`, build `2026.07.004`.

## Primer acceso

Use el usuario OWNER acordado para la implementación. La contraseña no se encuentra en texto plano dentro del proyecto; solo existe su hash Argon2id.

## Actualización en GitHub / Streamlit

1. Reemplace los archivos del repositorio por el contenido de esta versión.
2. Confirme que `requirements.txt` contiene `argon2-cffi`.
3. Suba los cambios a la rama principal.
4. Reinicie la aplicación en Streamlit Community Cloud.
5. Inicie sesión con `JDA` y valide el Centro Ejecutivo y Centro de Control.

## Seguridad

Antes de un uso productivo, cambie la contraseña OWNER desde una funcionalidad de cambio de contraseña o directamente mediante un proceso administrativo seguro. No publique bases de datos, secretos ni archivos reales en un repositorio público.
