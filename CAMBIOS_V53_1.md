# V53.1 · Corrección de navegación comercial

Se corrigió la excepción de Streamlit que aparecía al navegar desde Resumen
Comercial hacia Carga comercial u otra pestaña:

`st.session_state.project_nav_selector cannot be modified after the widget ...`

La navegación lateral y las pestañas superiores ahora envían una solicitud de
cambio mediante `nav_request`. El selector principal se sincroniza al comienzo
de la siguiente ejecución, antes de que Streamlit instancie el widget.

También se ajustó el botón para regresar al menú principal, evitando modificar
la llave del selector después de su creación.
