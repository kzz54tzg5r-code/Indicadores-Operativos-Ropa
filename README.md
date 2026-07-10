# Indicadores Cambios y Muertos v10.30

Correcciones:
- Une completa y permanentemente:
  - Resultados productividad
  - Resultados productividad 2
- Ya no elimina el histórico anterior al 29/06/2026.
- La nueva hoja solo reemplaza registros realmente duplicados.
- El Dashboard Ejecutivo vuelve a mostrar el acumulado desde la primera hasta la última fecha.
- Las tarjetas de semanas continúan mostrando las últimas cuatro semanas.
- Diagnóstico operativo separado para confirmar:
  - filas históricas;
  - filas nuevas;
  - total consolidado;
  - fecha mínima y máxima.

Actualización obligatoria:
1. Sustituir los archivos del repositorio.
2. Reiniciar Streamlit.
3. Borrar el archivo persistido.
4. Cargar nuevamente el Excel.
5. Procesar archivo.
6. Revisar Diagnóstico operativo — unión de hojas.
