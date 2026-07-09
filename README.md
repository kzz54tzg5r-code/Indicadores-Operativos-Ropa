# Indicadores Cambios y Muertos v10.18

Correcciones:
- Normaliza fechas operativas para evitar semanas 49 por fechas invertidas.
- Por Día usa comparación de fechas normalizada.
- Dev pzs se toma directo de comercial ya homologado por Fecha + Tienda.
- Dashboard vuelve a mostrar últimas 4 semanas reales detectadas en la base.
- % Procesado ya no duplica Pend. Ant. porque Total ya incluye el pendiente anterior.

Después de subir:
1. Reinicia la app.
2. Borra archivo persistido.
3. Carga nuevamente el Excel.
4. Procesar archivo activo.
