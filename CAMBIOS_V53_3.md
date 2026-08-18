# V53.3 · Reconocimiento de tiendas en PDF

Se agregó reconocimiento de los códigos usados en los nombres de los reportes
semanales: AGS, ARCO, ATE, CEN, ECA, IXTA, IZT, LEO, MIR, NAU, OLI, PUE,
Puebla Sur, QRO, TOL, VALL y VER.

Los PDF que ya están guardados se vuelven a analizar automáticamente y su
registro en `manifest.json` se actualiza cuando el nombre de tienda cambie de
"Tienda sin identificar" a la sucursal reconocida. No es necesario volver a
subirlos.

También se corrigió el corte actual para que una etiqueta "Sin semana" no tenga
prioridad sobre semanas ISO válidas como `2026-W34`.
