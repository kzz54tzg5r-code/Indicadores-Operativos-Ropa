# ORION MOBILE V4 · Ajustes Planeación Comercial

## Macro · Compañía
- Sugerido, DDI y Capacidad (Curva) muestran en texto pequeño el desglose Dama, Caballero e Infantil.
- Se agregó KPI de Ocupación = Existencia / Capacidad x 100, con ocupación por sección.
- Se retiraron las tarjetas macro Part. piezas, Part. inventario, Part. utilidad e Inversión identificada.
- Se retiraron las tarjetas grandes Dama/Caballero/Infantil.
- Las participaciones por sección quedan compactas: Part. pzas, Part. utilidad y Part. inventario.
- Se mantiene el detalle tabular por sección.

## Comparativo de tiendas
- DDI usa semáforo: 0–90 verde, 91–120 amarillo y >120 rojo.
- Se amplió el rango útil de la gráfica y se usa texto automático para evitar cortar el dato de la barra mayor en móvil.

## Modelos
- Campeones Top 50 conserva filtros y elimina de la tabla: % Part. sugerido, % Utilidad e Inversión.
- Lentos conserva Sugerido con 2 decimales y elimina % Utilidad.
- En alcance Compañía se consolida el mismo ID_ART entre tiendas: las piezas/métricas aditivas se suman y el modelo aparece una sola vez.
- Campeones y lentos se muestran sólo en Macro Compañía; se eliminaron sus repeticiones en Tiendas, Sección/Rubro y Ubicación/Área.

## Tiendas
- La primera tabla incorpora filtro General / Dama / Caballero / Infantil.
- Se eliminó la tabla adicional “Secciones de la tienda / alcance”.

## Sección / Rubro
- Se eliminó “Macro por sección”.
- Se eliminó Posiciones y se agregó Capacidad (Curva).
- Se eliminó Inversión.
- En General, % Utilidad es promedio simple de los PDF disponibles por rubro.
- DDI 91–120 se muestra en amarillo y >120 en rojo.
