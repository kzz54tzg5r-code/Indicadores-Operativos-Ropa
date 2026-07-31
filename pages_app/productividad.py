"""Presentación modular: Productividad.

La ruta productiva se mantiene conectada a la capa de compatibilidad V21 para
no eliminar funciones. La migración progresiva usa los servicios de ``services``.
"""
def render(context):
    handler=context.get("handler")
    if handler is None: raise RuntimeError("Ruta no configurada")
    return handler()
