# V49 — ORION Asistente Virtual

## Nuevo módulo
Se incorpora **ORION · Asistente** dentro del proyecto Muertos y Cambios.

### Principios
- Los números no los calcula el modelo: los calcula PS Operaciones Ropa.
- ORION recibe únicamente KPI y tablas agregadas del periodo solicitado.
- Respeta alcance del usuario y tiendas autorizadas.
- Si no existe información suficiente, no inventa datos.
- La consulta a OpenAI usa Responses API con `store=false`.
- Sin API key, ORION sigue respondiendo mediante un motor determinista verificado.

### Preguntas iniciales soportadas
- Operación: ingresos, acondicionado, ubicado y pendientes.
- Recuperación: conversión, recuperación económica, ranking y pendientes.
- Productividad: productividad global y ranking disponible.
- Recorridos: realizados, meta y cumplimiento.
- Ejecutivo: resumen y PS Score.
- Periodos: hoy, ayer, semana N, semana actual, mes actual y meses por nombre.
- Tiendas: detecta tienda mencionada en la pregunta.

### Retroalimentación
El usuario puede marcar una respuesta como útil/no útil. En respuestas no útiles puede indicar motivo y alternativa preferida. La retroalimentación se guarda en `data/config/orion_feedback.jsonl` y se usa como contexto para futuras respuestas del mismo tipo.

### Configuración OpenAI opcional
En Streamlit Secrets:

```toml
OPENAI_API_KEY = "sk-..."
ORION_MODEL = "gpt-5-mini"
```
