def es_cliente(u):    return hasattr(u, "cliente")
def es_farmacia(u):  return hasattr(u, "farmacia")
def es_repartidor(u): return hasattr(u, "repartidor")

# apps/orders/utils.py
# (Las 3 funciones 'es_cliente', 'es_farmacia', 'es_repartidor' ya existen)

def cart_context_processor(request):
    """
    Agrega el conteo de artículos del carrito al contexto de todas las plantillas.
    """
    cart_item_count = 0
    
    # Solo calculamos si el usuario es un cliente autenticado
    if request.user.is_authenticated and es_cliente(request.user):
        carrito_session = request.session.get('carrito', {})
        farmacias_data = carrito_session.get('farmacias', {})
        
        total_items = 0
        try:
            # Contamos cuántos items únicos hay en total, sumando los de cada farmacia
            for f_id, f_data in farmacias_data.items():
                total_items += len(f_data.get('items', {}))
        except Exception:
            total_items = 0 # En caso de que la estructura del carrito sea inválida
        
        cart_item_count = total_items
            
    return {
        'cart_item_count': cart_item_count
    }