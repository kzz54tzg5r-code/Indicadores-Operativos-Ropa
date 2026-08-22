# ORION MOBILE V6 · V73

## Corrección crítica de pantalla en blanco

- Se evita el ciclo de reruns durante la restauración del histórico comercial.
- `commercial_cloud_bootstrap` se marca antes de escribir `manifest.json` o `snapshots.json`.
- Se agregó `.streamlit/config.toml` con `fileWatcherType = "none"` para que las escrituras de datos de ejecución no reinicien el script.
- Se conserva la navegación, los cambios visuales y reglas comerciales de ORION_MOBILE_V5.
- Marcador visible actualizado a `V73 · ORION Mobile`.
