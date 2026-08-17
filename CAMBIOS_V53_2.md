# V53.2 · Menú lateral comercial reforzado

Se corrigió la ausencia visual del menú lateral azul en las páginas de Ventas
y Análisis Comercial.

La aplicación heredaba capas de estilos V30, V31 y V33 que ocultaban el
sidebar con reglas `!important`. El módulo ahora agrega un marcador comercial y
selectores CSS de mayor especificidad, por lo que el menú lateral conserva
prioridad aunque las reglas antiguas se carguen posteriormente.

La navegación incluye iconos y accesos a Resumen, Tiendas, Ubicaciones,
Modelos, Inventario, Oportunidades, Pronóstico, Histórico y Carga comercial.
Las pestañas horizontales permanecen como navegación secundaria.
