# Cambios V59 · Vistas operativas de tienda

## Objetivo

Transformar el módulo comercial en una herramienta sencilla para personal de tienda, supervisión y dirección. La lectura inicia con qué está pasando y termina con una acción concreta.

## Nuevo menú

1. **Mi tienda**: lectura de 30 segundos con sugerido/VPD, participación, inventario y acciones prioritarias.
2. **Qué vendo**: comparación por sección, ubicación o línea con participación en piezas, venta en pesos y utilidad.
3. **Qué resurtir**: ranking Sugerido/VPD con existencia, piso, bodega, días de inventario, prioridad y acción.
4. **Mis modelos**: Top 20 de Sugerido/VPD, Utilidad, Baja rotación e Inversión sin gráfico de dispersión.
5. **Dinero y utilidad**: comparación directa de participación en venta $ y participación en utilidad.
6. **Mi evolución**: tendencia semanal de sugerido/VPD, existencia y días de inventario.
7. **Carga PDF**: permanece separada y visible para administrador.

## Diseño y operación

- Se elimina el gráfico de puntos Venta vs. Inversión.
- Se utilizan barras horizontales con etiquetas directas.
- Las tablas se ordenan para facilitar la decisión.
- Las acciones se expresan en lenguaje operativo: Resurtir, Vigilar agotamiento, Subir de bodega a piso, Mantener o Contener/transferir.
- Los filtros globales mantienen la navegación Compañía → Tienda → Categoría → Línea → Modelo/SKU.
- El detalle de venta puede cambiar entre Sección, Ubicación y Línea.

## Integridad de los datos

- `Sugerido / VPD` se presenta como promedio diario de piezas.
- `% Piezas`, `% Venta` y `% Utilidad` se conservan como participaciones publicadas por el PDF.
- `% Utilidad` no se presenta como margen.
- La venta total en pesos y el margen quedan como `Información no disponible` cuando el PDF no contiene los importes base.
- En alcance Compañía, los porcentajes monetarios se identifican como promedio de participación entre tiendas y no como importe consolidado.

## Funciones conservadas

- Procesamiento PDF uno por uno.
- Guardado inmediato de cada resultado.
- Reanudación de archivos pendientes o con error.
- Histórico acumulable y respaldo.
- Navegación lateral visible y responsive.
