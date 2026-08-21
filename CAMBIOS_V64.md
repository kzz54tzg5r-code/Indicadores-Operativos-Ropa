# V64 · Planeación Comercial Macro → Micro

- Se incluyen en la versión los 17 PDF del corte 2026-W34 junto con sus snapshots normalizados, para que el corte no dependa de la sesión actual al desplegar esta versión.
- Modelos campeones: filtro independiente Dama / Caballero / Infantil y orden por Sug 7 o Utilidad.
- Modelos lentos: filtro independiente Dama / Caballero / Infantil y prioridad por Sug 7 menor o Inversión mayor.
- Sección / Rubro conserva el alcance de Tienda antes de agrupar y mantiene el orden por Sug 7.
- Ubicación / Área usa la tabla real “Ventas por Ubicación” del PDF; se elimina “Otras ubicaciones”.
- Se incorpora una tabla física separada de Mesas / Racks / Pasillos, ordenada de mayor a menor Sug 7.
- El parser ahora extrae la página de análisis por ubicación física del PDF.
- Encabezados de tablas comerciales en azul corporativo con texto blanco.
- Macro compañía reorganizado con tarjetas que sólo usan datos publicados: Existencia, Sug 7, DDI, Curva, participación de piezas, inventario, utilidad e inversión identificada.
- Dinero y utilidad elimina tarjetas de “Información no disponible”.
- Formato numérico conserva comas de miles, porcentajes y moneda.

## Persistencia
El corte 2026-W34 queda incluido físicamente en esta entrega. Para que futuras cargas semanales sobrevivan reinicios o redespliegues de Streamlit Cloud, sigue siendo necesario configurar una fuente persistente privada (el proyecto ya soporta Supabase Storage mediante secrets). Un disco temporal de Streamlit no puede convertirse en persistente sólo con código local.
