# PS Operaciones Ropa

Plataforma Integral de Gestión Operativa del área de Operaciones Ropa.

## Versión

- Versión: `0.4.0`
- Build: `2026.07.004`

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

- Centro Ejecutivo.
- Reportes diario, semanal y mensual.
- Conversión y recuperación económica.
- Productividad, recorridos y ranking.
- Macro por tienda y detalle por ID/SKU.
- Diagnóstico, usuarios y Centro de Control.
- Exportación PDF en reportes autorizados.

Consulte `MIGRACION_V0.4.md` para actualizar la aplicación.
