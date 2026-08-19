# Cambios V58 · Carga PDF recuperable

## Problema corregido

La carga de 17 PDF ejecutaba varias extracciones pesadas al mismo tiempo. En un servidor limitado de Streamlit Cloud esto podía saturar CPU o memoria y dejar la interfaz detenida en “Preparando 17 PDF para extracción”.

## Nuevo flujo de carga

- Procesa los PDF uno por uno para mantener estable el servidor.
- Muestra el número y nombre del archivo que se está procesando.
- Guarda el resultado y el snapshot inmediatamente después de cada PDF.
- Continúa con los demás archivos aunque uno presente error.
- Marca como `Procesando` el archivo activo y como `Error` cualquier fallo individual.
- Incluye el botón `Reanudar pendientes (N)` para continuar después de un reinicio o una interrupción.
- Reutiliza snapshots válidos y evita repetir trabajo ya terminado.
- Calcula el KPI de errores sólo sobre el corte vigente.

## Continuidad del diseño

V58 conserva la navegación y el análisis macro a micro de V57:

1. Periodo.
2. Tienda.
3. Categoría.
4. Línea.
5. Modelo / SKU.

También mantiene las vistas Radiografía, Catálogo, Planeación, Histórico y Carga PDF, así como el criterio PDF-only del reporte comercial.

## Nota operativa

La extracción completa de 17 PDF puede tardar varios minutos. La diferencia es que ahora existe avance visible y recuperación. Para conservar los cortes tras reinicios o nuevos despliegues debe configurarse el almacenamiento privado indicado por la aplicación.
