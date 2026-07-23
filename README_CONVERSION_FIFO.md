# v13.0 — Conversión y Recuperación FIFO

Solo se modificó la lectura comercial necesaria y las pestañas Conversión/Recuperación Económica.

- Match: Tienda + SKU (ID/Color) + Año ISO + Semana ISO.
- Conversión piezas = min(devoluciones, ventas).
- FIFO vectorizado por acumulados.
- Costo recuperado según costo de las devoluciones consumidas FIFO.
- Venta recuperada según importe unitario de las ventas utilizadas FIFO.
- Mensual/anual agregan hechos semanales; no hacen cruces entre semanas.
- Límites: conversión <= 100%, pendientes >= 0.

Es obligatorio volver a procesar el Excel para poblar SKU, descripción y costo.
