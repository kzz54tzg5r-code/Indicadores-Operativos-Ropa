# PS Operaciones Ropa

Plataforma Integral de Gestión Operativa del área de Operaciones Ropa.

## Versión

- Versión: `V55`
- Build: `Análisis Comercial Semanal · sólo PDF`

## Ejecutar localmente

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Seguridad

- Las contraseñas nuevas se almacenan con Argon2id.
- Los usuarios y alcances se administran en SQLite: `data/config/usuarios.db`.
- `config/usuarios.json` está obsoleto y no contiene credenciales.
- No suba archivos reales, bases de datos ni secretos a repositorios públicos.

## Módulos existentes

- Análisis Comercial Semanal con nueve vistas ejecutivas alimentadas sólo por PDF.
- Carga única de hasta 17 PDF con procesamiento paralelo, histórico acumulable y respaldo ZIP.
- Sincronización opcional con almacenamiento privado para conservar el histórico después de reinicios.
- Análisis por tienda, inventario, sección, ubicación, marca y modelo.
- Top 20 de Utilidad, Sugerido/VPD, Baja rotación e Inversión según el PDF.
- Inventario, cobertura, proyección de consumo y oportunidades operativas.
- Centro Ejecutivo.
- Reportes diario, semanal y mensual.
- Conversión y recuperación económica.
- Productividad, recorridos y ranking.
- Macro por tienda y detalle por ID/SKU.
- Diagnóstico, usuarios y Centro de Control.
- Exportación PDF en reportes autorizados.

Consulte `CAMBIOS_V55.md` para conocer el alcance del reporte comercial sólo PDF.
