# PS Operaciones Ropa V20.3

## Correcciones

- El saludo del encabezado y la bienvenida del Centro Ejecutivo usan la
  misma regla horaria.
- Recordarme mantiene la sesión durante 30 días.
- El usuario queda precargado al volver a la pantalla de acceso.
- La contraseña no se guarda en texto dentro de la aplicación; el campo
  utiliza `autocomplete=current-password` para permitir que el navegador
  la administre de forma segura.
- Se eliminó el spinner que dejaba la pantalla transparente.
- El procesamiento utiliza un panel de estado visible.
- Al finalizar se valida que el caché realmente exista.
- Si falla, se muestra el detalle de `config/ultimo_error_proceso.txt`.
