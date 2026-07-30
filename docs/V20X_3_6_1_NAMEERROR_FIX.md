# PS Operaciones Ropa V20X.3.6.1

## Corrección

La versión V20X.3.6 consultaba la variable `DATA_PAGES`, pero el conjunto se
había guardado accidentalmente con el nombre `ADMIN_WITHOUT_DATA_PAGES`.

Esto causaba:

`NameError: name 'DATA_PAGES' is not defined`

Se corrigió el nombre y se incluyó también la página `Reportes` dentro de las
pantallas que requieren consulta selectiva.
