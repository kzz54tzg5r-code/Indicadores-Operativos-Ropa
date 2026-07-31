# Migración desde V21 a V24
1. Respaldar la carpeta `data/` de V21.
2. Sustituir el código por el contenido de este ZIP.
3. Restaurar únicamente `data/uploads`, `data/cache` y la base de usuarios si ya estaba protegida.
4. No copiar archivos JSON con contraseñas antiguas.
5. Instalar `requirements.txt`.
6. Ejecutar `pytest -q`.
7. Ejecutar `streamlit run app.py`.
8. Validar OWNER, ADMIN, DIRECTOR, REGIONAL, TIENDA, SUPERVISOR y CONSULTA.
9. Validar que un usuario STORE no acceda a otra tienda.
10. Reprocesar el Excel si el esquema cacheado es incompatible.
