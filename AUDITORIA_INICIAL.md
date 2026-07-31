# Informe de auditoría inicial

## Estado recibido
El proyecto V21 conservaba una aplicación funcional extensa en un solo archivo de aproximadamente 9,900 líneas, con múltiples generaciones de CSS y rutas superpuestas. Se localizaron datos ficticios visibles en alertas, inteligencia, sesiones e histórico de descargas. También existían fórmulas comerciales heredadas no centralizadas.

## Correcciones V24
- Se creó una entrada de producción mínima y una capa de compatibilidad para no romper funcionalidades.
- Se centralizaron identidad, rutas, metas, roles y estados.
- Se implementaron controles de alcance a nivel de DataFrame.
- Se creó base SQLite para auditoría, usuarios, metas, descargas y estado.
- Se sustituyeron datos demo visibles por información real o mensajes sin información.
- Se unificó conversión/recuperación semanal y productividad.
- Se añadieron pruebas y exportadores centrales.

## Limitaciones verificadas
La migración completa de las ~9,900 líneas a 19 páginas independientes no puede considerarse terminada sin una prueba funcional de cada flujo con el Excel real de producción. V24 conserva `legacy_app.py` como capa de compatibilidad para evitar pérdida de funcionalidad. Los módulos nuevos están listos para migración progresiva y ya concentran reglas críticas.
