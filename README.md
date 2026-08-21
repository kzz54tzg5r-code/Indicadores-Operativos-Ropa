# PS Operaciones Ropa

Plataforma Integral de Gestión Operativa del área de Operaciones Ropa.

## Versión

- Versión: `V69`
- Build: `ORION Mobile · navegación inferior y tarjetas de decisión`

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
- Barra inferior móvil: Inicio, Tiendas, Secciones, Modelos y Más.
- Tablas convertidas automáticamente en tarjetas compactas en teléfonos.
- Filtros globales persistentes entre las pantallas comerciales.
- Menú operativo: Mi tienda, Qué vendo, Qué resurtir, Mis modelos, Dinero y utilidad, Mi evolución y Carga PDF para administrador.
- Filtros globales persistentes y breadcrumb para conservar el contexto.
- Diseño concentrado en tarjetas compactas, tablas maestras, semáforos y una sola gráfica comparativa a nivel compañía.
- Carga de hasta 17 PDF con procesamiento incremental, reanudación automática, histórico acumulable y respaldo ZIP.
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

Consulte `CAMBIOS_V59.md` para conocer las vistas operativas, `CAMBIOS_V58.md` para la carga PDF recuperable y `CAMBIOS_V57.md` para la navegación macro a micro.
