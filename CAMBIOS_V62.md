# CAMBIOS V62 — FORMATO COMERCIAL Y CORRECCIÓN UBICACIÓN / ÁREA

## Correcciones
- Se estandarizó el nombre visible del indicador de sugerido a **Sug 7** en las vistas V61.
- Todas las tablas comerciales ahora muestran piezas y cantidades como números completos con separador de miles y sin decimales.
- Los porcentajes se muestran con símbolo `%` y un decimal.
- Los importes monetarios, incluida **Inversión**, se muestran con `$` y separador de miles.
- Se corrigió el fallo `KeyError: Sug` en **Ubicación / Área**. La vista ya no intenta consultar una columna renombrada que no exista.
- Si un área seleccionada no contiene registros o no tiene Sug 7 publicado, se muestra un mensaje informativo en lugar de romper la página.
- Las tablas de Tiendas, Sección/Rubro, Campeones, Lentos y Ubicación/Área utilizan la misma convención visual.

## Nota técnica
El dato fuente continúa normalizado internamente como `VPD` para conservar compatibilidad con los PDF y cálculos existentes; únicamente su nombre comercial visible es **Sug 7**.
