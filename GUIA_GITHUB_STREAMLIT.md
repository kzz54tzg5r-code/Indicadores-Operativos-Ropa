# Publicación en GitHub y Streamlit Cloud
1. Descomprime el ZIP y copia su contenido en la raíz del repositorio.
2. Confirma que `app.py` y `requirements.txt` estén en la raíz.
3. No subas `data/config/*.db`, `data/uploads/*`, `.streamlit/secrets.toml` ni contraseñas.
4. En GitHub: `git add .`, `git commit -m "PS Operaciones Ropa V24 Producción"`, `git push origin main`.
5. En Streamlit Cloud selecciona repositorio, rama `main` y archivo `app.py`.
6. En Advanced settings configura Python 3.13 si está disponible; evita versiones preliminares.
7. Configura secretos desde Streamlit Cloud, nunca dentro del repositorio.
8. Reinicia la app y valida primero con un archivo pequeño; después procesa el archivo real por etapas.
