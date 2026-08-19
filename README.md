# PS Operaciones Ropa

Plataforma Integral de Gestión Operativa del área de Operaciones Ropa.

## Versión

- Versión: `V57`
- Build: `Planeación Comercial · navegación macro a micro`

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

- Planeación Comercial con navegación continua: Compañía → Tienda → Categoría → Línea → Modelo.
- Menú simplificado: Radiografía, Catálogo, Planeación, Histórico y Carga PDF.
- Filtros globales persistentes y breadcrumb para conservar el contexto.
- Diseño concentrado en tarjetas compactas, tablas maestras, semáforos y una sola gráfica comparativa a nivel compañía.
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

Consulte `CAMBIOS_V57.md` para conocer el alcance de la navegación macro a micro.
