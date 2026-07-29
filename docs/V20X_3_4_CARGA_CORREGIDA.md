# PS Operaciones Ropa V20X.3.4

## Corrección aplicada

La navegación tenía dos valores simultáneos:

- Radio lateral para escritorio.
- Selectbox para móvil.

Al seleccionar `Carga de Excel`, el radio cambiaba correctamente, pero el
selectbox móvil conservaba `Centro Ejecutivo` y sobrescribía la página elegida.

Esta versión usa una sola fuente de navegación, por lo que:

- `Carga de Excel` abre realmente la pantalla de carga.
- Las páginas administrativas pueden abrirse sin archivo activo.
- No se requieren callbacks.
- Se conservan el procesamiento por etapas y las correcciones Low Memory.
