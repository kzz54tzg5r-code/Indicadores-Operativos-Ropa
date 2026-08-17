# PS Operaciones Ropa

Plataforma Integral de Gestión Operativa del área de Operaciones Ropa.

## Versión

- Versión: `V53.1`
- Build: `Ventas y Análisis Comercial · navegación Streamlit corregida`

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

- Ventas y Análisis Comercial con ocho vistas ejecutivas.
- Carga mensual de ventas y capacidades/existencias.
- Carga semanal de hasta 17 PDF, con histórico acumulable y respaldo ZIP.
- Análisis por tienda, sección, ubicación y modelo.
- Top 20 de campeones y lentos por Sugerido/VPD o Utilidad.
- Inventario, cobertura, oportunidades y pronóstico comercial.
- Centro Ejecutivo.
- Reportes diario, semanal y mensual.
- Conversión y recuperación económica.
- Productividad, recorridos y ranking.
- Macro por tienda y detalle por ID/SKU.
- Diagnóstico, usuarios y Centro de Control.
- Exportación PDF en reportes autorizados.

Consulte `CAMBIOS_V53.md` y `CAMBIOS_V53_1.md` para conocer el nuevo flujo comercial y su corrección de navegación.
