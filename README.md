# Indicadores Cambios y Muertos v11.8

Cambios:
- Acceso a pantalla completa.
- Título de acceso: Operaciones Ropa / Indicadores.
- Texto negro visible en usuario y contraseña.
- Encabezado posterior al acceso con usuario y fecha inferior.
- Menú desplegable de indicadores.
- Menú Administración para cargar, procesar o borrar el Excel.
- El menú Administración solo aparece para Administrador.
- La gráfica Por Día usa únicamente ingresos del día; ya no usa el saldo pendiente anterior como línea de ingresos.
- La gráfica mensual usa únicamente ingresos del mes.

La cifra alta en el gráfico diario se producía porque la línea utilizaba la columna Total,
que incluía ingresos del día más el pendiente acumulado anterior. Ahora utiliza
Ingresos periodo.
