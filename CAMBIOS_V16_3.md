# PS Operaciones Ropa v16.3

Correcciones incluidas:

- Saludo dinámico:
  - Buenos días
  - Buena tarde
  - Buenas noches
- Usuario superior sin deformarse ni dividirse en varias líneas.
- Letras del menú lateral completamente blancas.
- Ocultamiento del toolbar y del botón Stop de Streamlit.
- Login con logo Price Shoes ajustado.
- Imagen boutique tomada de la maqueta aprobada.
- Caché atómico para evitar archivos parquet incompletos.
- Respaldo automático en pickle cuando parquet no puede guardar un tipo.
- Procesamiento por etapas con liberación de memoria.
- Registro del paso exacto que falla en `config/ultimo_error_proceso.txt`.
