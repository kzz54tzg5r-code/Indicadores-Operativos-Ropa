# PS Operaciones Ropa V20X Enterprise

## Corrección principal

Se definieron y centralizaron:

- `PROCESS_STATUS_FILE`
- `PROCESS_LOCK_FILE`
- `PROCESS_LOG_FILE`

## Estabilización

- Estado persistente del procesamiento.
- Escritura atómica del archivo de estado.
- Bloqueo para impedir dos procesos simultáneos.
- Liberación del bloqueo al terminar o al fallar.
- Recuperación automática de bloqueos abandonados.
- Reutilización del caché cuando el archivo no cambió.
- Conserva el menú lateral corregido.
- Conserva la jerarquía Propietario > Administrador > Consulta.
