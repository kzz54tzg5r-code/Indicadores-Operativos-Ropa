# v9.6 Fix carga AgGrid

El log mostraba:
warning: streamlit-aggrid==1.1.8 is yanked (bugged)

Cambio:
- requirements.txt ahora usa streamlit-aggrid==1.2.0.post2.
- Evita el paquete yanked que puede dejar la app cargando sin error visible.

Sube app.py y requirements.txt a GitHub.
