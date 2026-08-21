# V71 — ORION Mobile

- Se corrigió la navegación móvil: ya no se sobrescribe la pestaña seleccionada en cada rerun.
- La barra móvil usa una llave independiente por pantalla y callback de navegación para que Inicio, Tiendas, Secciones, Modelos y Más respondan correctamente.
- Se agregó `Menú` como acceso directo al menú principal del portafolio.
- La navegación móvil se crea antes del contenido y queda fuera del flujo visual cuando se fija, evitando el bloque vacío que aparecía en Safari.
- Se agregó control de `overscroll-behavior` para reducir el espacio vacío al arrastrar de más en iPhone/iPad.
- En Dama / Caballero / Infantil se quitó la referencia `Inv.` de las tarjetas y `% Part Inventario` de la tabla de sección.
- Se conserva Existencia, Piso, Bodega, Sugerido, DDI, % Utilidad y % Part. Piezas.
