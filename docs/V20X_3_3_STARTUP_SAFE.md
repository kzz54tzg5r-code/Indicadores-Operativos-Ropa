# PS Operaciones Ropa V20X.3.3

## Corrección de inicio y navegación

- Se eliminaron los callbacks `on_change` del menú.
- La navegación usa directamente el valor devuelto por `st.radio` y
  `st.selectbox`.
- Se usan claves nuevas de widget para evitar estados incompatibles de
  versiones anteriores.
- Se conserva el procesamiento Low Memory y las correcciones de esquema.
- Esta versión puede abrirse incluso cuando el navegador conserva una sesión
  antigua.
