# PS Operaciones Ropa V20X.2.1

## Corrección del error “Oh no”

La aplicación se detenía al abrir una sesión nueva porque el formulario de
acceso utilizaba el argumento `autocomplete` en `st.text_input`.

Streamlit 1.59.1 no admite ese argumento, por lo que se generaba un error
antes de mostrar el login.

## Conservado

- Procesamiento por etapas.
- Avance recuperable.
- Menú lateral.
- Sesión persistente mediante token.
- Usuario recordado mediante parámetro seguro.
- Roles Propietario, Administrador y Consulta.
