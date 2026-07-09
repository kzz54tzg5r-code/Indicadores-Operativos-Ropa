# Indicadores Cambios y Muertos v10.19

Correcciones:
- Dev pzs en Por Día ahora filtra por Fecha_txt YYYY-MM-DD, igual que Diagnóstico.
- Si hay fecha invertida por selección, intenta rescate día/mes.
- Fecha por defecto de Por Día toma la última fecha comercial disponible para que Dev pzs no arranque en 0.
- Gráfico: barras habilitadas usan el mismo azul de la tabla y la línea queda en azul claro.
- Operación se normaliza antes de guardar y al leer cache.

Después de subir:
1. Reinicia la app.
2. Borra archivo persistido.
3. Carga nuevamente el Excel.
4. Procesar archivo activo.
