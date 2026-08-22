# ORION MOBILE V7 · Corrección escritorio

- Corrección específica para escritorio: el área central de Análisis Comercial ya no compite con un segundo shell heredado.
- `commercial/ui.py` queda como única fuente del layout del sidebar y del panel principal comercial.
- El panel principal fuerza `display`, `visibility`, `opacity`, ancho y posición correctos para viewport >= 901 px.
- Las páginas comerciales dejan de cargar el Excel operativo heredado antes de abrir; usan exclusivamente PDF/snapshots.
- Si ya existen `manifest.json` y `snapshots.json` locales, no se bloquea el primer render esperando restauración remota.
- Se conservan todos los ajustes móviles y funcionales de V6.
