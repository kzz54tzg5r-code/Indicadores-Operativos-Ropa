# V75 · Acordeón Comercial + corrección escritorio

## Acordeón Comercial
- Se agrega una pestaña inmediatamente después de **Macro compañía**.
- La estructura toma como referencia el formato "ACORDEÓN DE INFORMACIÓN ROPA" y se reorganiza para Streamlit responsive.
- Incluye bloques de metas/venta, rankings, marcas campeonas, resumen general, FINDE/10 Pagos, devoluciones, ubicaciones campeonas, modelos campeones/lentos, análisis por rubro y plan de acción.
- Los campos que todavía no tienen una fuente auditable (presupuesto/meta, FINDE, 10 Pagos, devoluciones y Entallado/Surtido/Exhibido) se muestran como pendientes y no se inventan.

## Ventas mensuales
- La carga de ventas solicita **año + mes**.
- Para el mes en curso, cada nueva carga reemplaza lógicamente a la anterior para ese mismo periodo usando la versión más reciente.
- A partir del día 1 del mes siguiente, una carga del mes anterior se clasifica como **Cierre mensual**.
- Ejemplo: agosto 2026 permanece como acumulado durante agosto; el archivo cargado desde el 1 de septiembre para `2026-08` queda como cierre definitivo.
- El Acordeón usa el mes seleccionado y compara contra el mismo mes del año anterior cuando existe fuente.

## Escritorio
- Las páginas de Análisis Comercial se renderizan por una ruta directa antes de la capa operativa heredada.
- Después de renderizar la página comercial se detiene la ejecución de estilos/cargas heredadas que podían dejar el panel central en blanco.
- Si ocurre una excepción comercial, ahora se muestra el error en pantalla y se registra como `[COMMERCIAL][ERROR]` en el log, en lugar de dejar una vista vacía.

## Logo
- El logo del sidebar dejó de usar `st.image` y ahora se renderiza como HTML embebido.
- Esto elimina el botón/overlay de Streamlit para ampliar o "ver imagen".

## Navegación móvil
- Se conserva la navegación inferior y se agrega acceso a **Acordeón**.
