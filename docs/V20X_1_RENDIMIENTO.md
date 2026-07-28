# V20X.1 Rendimiento

Mejoras aplicadas:

- Resultados productividad y Resultados productividad 2 usan Calamine.
- Plantilla usa Calamine.
- OpenPyXL queda únicamente como respaldo.
- Se elimina una segunda lectura SHA-256 del archivo completo.
- Guardado atómico del Excel.
- Si el archivo es idéntico, se reutiliza el caché.
- La primera carga de un archivo nuevo todavía requiere leer y transformar
  sus hojas; las siguientes cargas deben ser considerablemente más rápidas.
