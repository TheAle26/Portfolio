import decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from .models import Pedido, DetallePedido, StockMedicamento,Farmacia,Cliente, Medicamento
from django.views.generic import DetailView
from apps.accounts.models import ObraSocial, Repartidor
from apps.orders.utils import es_cliente, es_farmacia, es_repartidor
from .forms import PedidoForm, EditStockMedicamentoForm, AddStockMedicamentoForm, FarmaciaAceptarPedidoForm
from django.db import transaction, IntegrityError
from django.db.models import F, Q, IntegerField, ExpressionWrapper, DecimalField
from django.contrib import messages
from django.db.models import Case, When
from django.shortcuts import render
from django.http import JsonResponse
import os

@login_required
def panel_principal(request):
    if es_cliente(request.user):
        return redirect("cliente_panel")
    elif es_farmacia(request.user):
        return redirect("farmacia_panel")
    elif es_repartidor(request.user):
        return redirect("repartidor_panel")
    else:
        return HttpResponseForbidden("Perfil no reconocido.")


    ## nose como usar esto, lo hice mas abajo como Cliente_ver_pedido
class MedicamentoDetailView(DetailView):
    model = Medicamento
    template_name = 'orders/cliente/medicamento_detalle.html' 
    context_object_name = 'medicamento'

# ---------- CLIENTE ----------

@login_required
def cliente_panel(request):
    if not es_cliente(request.user): return HttpResponseForbidden("Solo clientes")
    # Ordenar por estado según la prioridad deseada y luego por fecha de creación
    pedidos = (
        Pedido.objects.filter(cliente=request.user.cliente)
        .annotate(
            prioridad_estado=Case(
                When(estado="PENDIENTE", then=0),
                When(estado="ACEPTADO", then=1),
                When(estado="EN_CAMINO", then=2),
                When(estado="ENTREGADO", then=3),
                When(estado="RECHAZADO", then=4),
                default=5,
                output_field=IntegerField(),
            )
        )
        .order_by('prioridad_estado', 'creado')
    )

    return render(request, "orders/cliente/panel.html", {"pedidos": pedidos})

# orders/views.py
def _recalculate_cart_totals(carrito_sesion):
    """
    Recalcula todos los subtotales y el total general del carrito en la sesión.
    También añade una clave 'subtotal' a CADA item.
    """
    total_general = decimal.Decimal('0.0')
    
    # Usamos list() para poder eliminar farmacias si quedan vacías
    for f_id in list(carrito_sesion['farmacias'].keys()):
        f_data = carrito_sesion['farmacias'][f_id]
        subtotal_farmacia = decimal.Decimal('0.0')
        
        # Usamos list() para poder eliminar items
        for i_id in list(f_data['items'].keys()):
            i_data = f_data['items'][i_id]
            
            # Calcular subtotal del item
            subtotal_item = decimal.Decimal(i_data['precio_unitario']) * i_data['cantidad']
            i_data['subtotal'] = str(subtotal_item) # <-- Total por medicamento
            subtotal_farmacia += subtotal_item
        
        # Si la farmacia ya no tiene items, la eliminamos del carrito
        if not f_data['items']:
            carrito_sesion['farmacias'].pop(f_id)
        else:
            f_data['subtotal'] = str(subtotal_farmacia)
            total_general += subtotal_farmacia

    carrito_sesion['total_general'] = str(total_general)
    return carrito_sesion

@login_required
def _add_to_cart_logic(request, stock_id, cantidad):
    """
    Función auxiliar para agregar un item al carrito de la sesión.
    Maneja el stock y los mensajes de error/éxito."""
    
    try:
        stock_item = get_object_or_404(StockMedicamento, id=stock_id)

        # 1. Validar stock
        if stock_item.stock_actual < cantidad:
            messages.error(request, f"No hay stock suficiente para {stock_item.medicamento.nombre_comercial}.")
            return False # Indicar que falló

        # 2. Obtener carrito de la sesión (con strings para Decimal)
        carrito_sesion = request.session.get('carrito', {'farmacias': {}, 'total_general': '0.0'})

        farmacia_id = str(stock_item.farmacia.id)
        stock_id_str = str(stock_item.id)

        # 3. Obtener sub-carrito de la farmacia
        farmacia_data = carrito_sesion['farmacias'].get(farmacia_id, {
            'nombre_farmacia': stock_item.farmacia.nombre,
            'subtotal': '0.0',
            'items': {}
        })

        # 4. Obtener item (convirtiendo Decimal a string)
        item_data = farmacia_data['items'].get(stock_id_str, {
            'nombre': stock_item.medicamento.nombre_comercial,
            'precio_unitario': str(stock_item.precio), # Usar str()
            'stock_id': stock_item.id,
            'cantidad': 0
        })

         # 5. Actualizar cantidad
        item_data['cantidad'] += cantidad
        farmacia_data['items'][stock_id_str] = item_data
        carrito_sesion['farmacias'][farmacia_id] = farmacia_data

        # 6. REEMPLAZAR el cálculo de total anterior por esto:
        carrito_sesion = _recalculate_cart_totals(carrito_sesion)

        # 7. Guardar en la sesión
        request.session['carrito'] = carrito_sesion
        request.session.modified = True

        messages.success(request, f"{stock_item.medicamento.nombre_comercial} agregado al carrito.")
        return True

    except Exception as e:
        messages.error(request, f"Error al agregar al carrito: {e}")
        return False
## me gustaria en realidad que dentro de la view de ver/ buscar remedias, al hacer click en el boton,
# la otra view detecte ese post, tome los datos del  stock_id y se los pase a esta funcion,
# y que esta no tenga return, simplemente ponga el mensajito de agregado


@login_required
def update_cart_item(request, stock_id_str):
    """
    Actualiza la cantidad de un ítem en el carrito.
    """
    if request.method == 'POST':
        
        # 💥 SOLUCIÓN: Buscar el nombre del input específico, ej: "cantidad-123"
        cantidad_input_name = f"cantidad-{stock_id_str}"
        
        try:
            # Leer la cantidad de ESE input específico
            cantidad = int(request.POST.get(cantidad_input_name, 1))
        except ValueError:
            messages.error(request, "Cantidad inválida.")
            return redirect('ver_carrito')

        # ... (El resto de tu lógica de 'update_cart_item' es correcta) ...
        # (Buscar carrito, validar stock, recalcular, guardar sesión)
        carrito = request.session.get('carrito')
        if not carrito:
            return redirect('ver_carrito')

        if cantidad == 0:
            return remove_cart_item(request, stock_id_str)
        
        if cantidad < 0:
            messages.error(request, "Cantidad inválida.")
            return redirect('ver_carrito')

        item_encontrado = False
        for f_id, f_data in carrito['farmacias'].items():
            if stock_id_str in f_data['items']:
                
                try:
                    stock_obj = StockMedicamento.objects.get(id=int(stock_id_str))
                    if stock_obj.stock_actual < cantidad:
                        messages.error(request, f"Stock insuficiente (Máx: {stock_obj.stock_actual}).")
                        return redirect('ver_carrito')
                except StockMedicamento.DoesNotExist:
                    messages.error(request, "El producto ya no existe.")
                    return redirect('ver_carrito')

                f_data['items'][stock_id_str]['cantidad'] = cantidad
                item_encontrado = True
                break
        
        if item_encontrado:
            request.session['carrito'] = _recalculate_cart_totals(carrito)
            request.session.modified = True
            messages.success(request, "Cantidad actualizada.")
        
    return redirect('ver_carrito')

@login_required
def remove_cart_item(request, stock_id_str):
    """
    Elimina un ítem del carrito, sin importar la cantidad.
    """
    carrito = request.session.get('carrito')
    if not carrito:
        return redirect('ver_carrito')

    item_nombre = "Producto"
    item_eliminado = False
    
    # Buscar el ítem y eliminarlo
    for f_id, f_data in carrito['farmacias'].items():
        if stock_id_str in f_data['items']:
            item_data = f_data['items'].pop(stock_id_str) # <-- Elimina el ítem
            item_nombre = item_data.get('nombre', 'Producto')
            item_eliminado = True
            break # Ítem encontrado y eliminado

    if item_eliminado:
        # Recalcular (esto también eliminará la farmacia si queda vacía)
        request.session['carrito'] = _recalculate_cart_totals(carrito)
        request.session.modified = True
        messages.success(request, f"{item_nombre} eliminado del carrito.")

    return redirect('ver_carrito')

@login_required
def ver_carrito(request):
    carrito_session = request.session.get('carrito', {'farmacias': {}})
    default_direccion = ""
    if hasattr(request.user, 'cliente'):
        default_direccion = request.user.cliente.direccion
    total_general_str = carrito_session.get('total_general', '0.0')

    carrito_contexto = {
        'farmacias': [],
        # 2. Convertir el total de vuelta a un número (Decimal)
        'total_general': decimal.Decimal(total_general_str)
    }
    
    hay_items_con_receta = False

    for farmacia_id, farmacia_data in carrito_session['farmacias'].items():
        items_contexto = []
        for item_id, item_data in farmacia_data['items'].items():
            try:
                # Obtenemos el objeto real del inventario
                stock_item = StockMedicamento.objects.select_related('medicamento').get(id=item_id)
                
                precio_unitario = decimal.Decimal(item_data['precio_unitario'])
                cantidad = int(item_data['cantidad'])

               
                subtotal_item = precio_unitario * cantidad
                
               
                item_data['stock_obj'] = stock_item
                item_data['precio_unitario'] = precio_unitario
                item_data['subtotal'] = subtotal_item 
                
                # --- FIN DE LA SOLUCIÓN ---
                items_contexto.append(item_data)
                
                if stock_item.medicamento.requiere_receta:
                    hay_items_con_receta = True
                    
            except StockMedicamento.DoesNotExist:
                pass 
        
        farmacia_data['items_enriquecidos'] = items_contexto
        carrito_contexto['farmacias'].append(farmacia_data)

    context = {
        'carrito_data': carrito_contexto,
        'total_general': carrito_contexto['total_general'],
        'hay_items_con_receta': hay_items_con_receta,
        'default_direccion': default_direccion
    }
    
    return render(request, 'orders/cliente/carrito_detalle.html', context)


# orders/views.py

@login_required
@transaction.atomic
def finalizar_compra_view(request):
    
    if request.method != 'POST':
        return redirect('ver_carrito')

    carrito = request.session.get('carrito')
    
    if not carrito or not carrito.get('farmacias'):
        messages.error(request, "Tu carrito está vacío.")
        return redirect('ver_carrito')
    direccion_validada = request.POST.get('direccion_entrega')
    if not direccion_validada:
        messages.error(request, "Por favor, completa la dirección de entrega.")
        return redirect('ver_carrito')
    try:
        pedidos_creados = []
        
        for farmacia_id, farmacia_data in carrito['farmacias'].items():
            farmacia_obj = get_object_or_404(Farmacia, id=farmacia_id)

            # No permitir compras a farmacias que no estén validadas
            if not getattr(farmacia_obj, 'valido', False):
                raise Exception(f"No es posible comprar a la farmacia '{farmacia_obj.nombre}' porque no está validada.")

            # Asegurarse de enlazar el perfil Cliente (no el User)
            cliente_profile = getattr(request.user, 'cliente', None)
            if cliente_profile is None:
                raise Exception("Debe iniciar sesión como cliente para finalizar la compra.")
            
            # Iterar sobre los items de la sesión
            for item_id, item_data in farmacia_data['items'].items():
                stock = StockMedicamento.objects.select_for_update().get(id=item_id)
                
                # (Validación de Stock)
                if stock.stock_actual < item_data['cantidad']:
                    raise Exception(f"Stock insuficiente para {stock.medicamento.nombre_comercial}.")
                
                receta_para_adjuntar = None # Por defecto es Nulo
                
                # 1. Chequear si el medicamento REQUIERE receta
                if stock.medicamento.requiere_receta:
                    # 2. Construir el 'name' del input del formulario
                    file_input_name = f"receta_{item_id}" 
                    
                    # 3. Obtener el archivo de request.FILES
                    receta_file = request.FILES.get(file_input_name)
                    
                    # 4. Validar que el archivo SÍ FUE ENVIADO
                    if not receta_file:
                        raise Exception(f"Falta adjuntar la receta para {stock.medicamento.nombre_comercial}.")
                    
                    
                    ext = os.path.splitext(receta_file.name)[1].lower()
                    if ext not in ['.pdf', '.jpg', '.jpeg', '.png']:
                        raise Exception(f"El archivo de receta para {stock.medicamento.nombre_comercial} no es válido. Solo se aceptan PDF o imágenes.")

                    receta_para_adjuntar = receta_file
                nuevo_pedido = Pedido.objects.create(
                cliente=cliente_profile,
                farmacia=farmacia_obj,
                estado='PENDIENTE', 
                total=farmacia_data.get('subtotal', 0),
                direccion=direccion_validada
                )
                
                DetallePedido.objects.create(
                    pedido=nuevo_pedido,
                    medicamento=stock.medicamento,
                    cantidad=item_data['cantidad'],
                    precio_unitario_snapshot=stock.precio,
                    receta_adjunta=receta_para_adjuntar # <-- Se guarda el archivo
                )
                

                # # (Descuento de Stock)
                # stock.stock_actual = F('stock_actual') - item_data['cantidad']
                # stock.save(update_fields=['stock_actual'])

            pedidos_creados.append(nuevo_pedido.id)

        # (Limpiar sesión y redirigir)
        del request.session['carrito']
        request.session.modified = True
        
        messages.success(request, f"Pedido confirmado. Se generaron {len(pedidos_creados)} pedidos correctamente.")
        return redirect('cliente_panel')

    except Exception as e:
        # Captura "Stock insuficiente" O "Falta adjuntar la receta"
        messages.error(request, str(e))
        return redirect('ver_carrito')
    
@login_required
def buscar_medicamentos(request):
    
    # --- Lógica de "Agregar al Carrito" (POST) ---
    if request.method == 'POST':
        stock_id = request.POST.get('stock_id')
        cantidad = int(request.POST.get('cantidad', 1))
        
        if stock_id:
            # Llamamos a la lógica auxiliar
            _add_to_cart_logic(request, stock_id, cantidad)
            
            # IMPORTANTE: Usamos el patrón "POST-Redirect-GET"
            # Redirigimos de vuelta a la MISMA página de búsqueda (con los filtros GET).
            # Esto evita que el formulario se reenvíe si el usuario recarga la página.
            query_params = request.GET.urlencode()
            return redirect(f"{request.path}?{query_params}")

    # --- Lógica de Búsqueda (GET) ---
    # Esta parte se ejecuta si el método es GET,
    # o después del redirect del POST.
    
    query = request.GET.get('q', '')
    obra_social_id = request.GET.get('obra_social_id', '')
    
    obras_sociales = ObraSocial.objects.all()
    
    resultados = StockMedicamento.objects.select_related('medicamento', 'farmacia').all()

    if query:
        resultados = resultados.filter(
            Q(medicamento__nombre_comercial__icontains=query) |
            Q(medicamento__principio_activo__icontains=query)
        )
    if obra_social_id:
        resultados = resultados.filter(
            farmacia__obras_sociales__id=obra_social_id
        )
    
    resultados = resultados.filter(
        farmacia__valido=True, 
        stock_actual__gt=0
    ).distinct()

    context = {
        'query': query,
        'obras_sociales': obras_sociales,
        'selected_obra_social': int(obra_social_id) if obra_social_id else None,
        'medicamentos_stock': resultados[:50],
    }
    return render(request, 'orders/cliente/buscar_medicamentos.html', context)
    
    
def cliente_ver_pedido(request, pedido_id):
    if not es_cliente(request.user):
        return HttpResponseForbidden("Solo clientes")

    pedido = get_object_or_404(
        Pedido,
        id=pedido_id,
        cliente=request.user.cliente
    )

    # Anotar subtotal por detalle para mostrar en la plantilla y evitar cálculos en el template
    detalles = (
        DetallePedido.objects.filter(pedido=pedido)
        .select_related('medicamento')
        .annotate(
            subtotal_calc=ExpressionWrapper(
                F('cantidad') * F('precio_unitario_snapshot'),
                output_field=DecimalField(max_digits=12, decimal_places=2)
            )
        )
    )

    context = {
        'pedido': pedido,
        'detalles': detalles
    }
    return render(request, 'orders/cliente/ver_pedido.html', context)


# ---------- FARMACIA ----------
@login_required
def farmacia_panel(request):
    if not es_farmacia(request.user): 
        return HttpResponseForbidden("Solo farmacias")
    # En el panel principal solo mostramos acciones rápidas y enlaces
    # La lista de pedidos se muestra en la vista dedicada 'farmacia_pedidos'
    return render(request, "orders/farmacia/farmacia_panel.html")


@login_required
def farmacia_pedidos_entrantes(request):
    """Vista dedicada para que la farmacia vea sus pedidos (entrantes).
    Muestra todos los pedidos de la farmacia, priorizando los pendientes.
    """
    if not es_farmacia(request.user):
        return HttpResponseForbidden("Solo farmacias")

    todos_los_pedidos = Pedido.objects.filter(farmacia=request.user.farmacia)

    pedidos_ordenados = todos_los_pedidos.annotate(
        prioridad_estado=Case(
            When(estado="PENDIENTE", then=0),
            When(estado="ACEPTADO", then=1),
            When(estado="EN_CAMINO", then=2),# Los PENDIENTE van primero
            default=3 # El resto va después
        )
    ).order_by('prioridad_estado', 'creado') # Ordena por prioridad, y luego por fecha

    # Pasa la lista completa y ordenada a la plantilla
    return render(request, "orders/farmacia/pedidos_entrantes.html", {"pedidos": pedidos_ordenados})

@login_required
def farmacia_aceptar(request, pedido_id):
    if not es_farmacia(request.user): 
        return HttpResponseForbidden("Solo farmacias")

    pedido = get_object_or_404(
        Pedido, 
        id=pedido_id, 
        estado="PENDIENTE", 
        farmacia=request.user.farmacia 
    )
    if request.method != "POST":
        return redirect("farmacia_pedidos")

    # 1) Validar casillas por cada ítem que requiere receta
    faltan_confirmar = []
    faltan_adjuntos = []
    for item in pedido.items.select_related("medicamento"):
        if item.medicamento.requiere_receta:
            # a) Debe existir la receta adjunta (archivo)
            if not item.receta_adjunta:
                faltan_adjuntos.append(item.medicamento.nombre_comercial)
            # b) Debe marcarse la casilla del ítem
            if not request.POST.get(f"confirmar_receta_{item.id}"):
                faltan_confirmar.append(item.medicamento.nombre_comercial)

    if faltan_adjuntos:
        messages.error(
            request,
            "No se puede aceptar: faltan recetas adjuntas para: " + ", ".join(faltan_adjuntos)
        )
        return redirect("farmacia_pedidos")

    if faltan_confirmar:
        messages.error(
            request,
            "Debés confirmar las recetas de: " + ", ".join(faltan_confirmar)
        )
        return redirect("farmacia_pedidos")

    # 2) Validar stock (usa los helpers del modelo)
    ok, faltantes = pedido.validar_stock()
    if not ok:
        messages.error(
            request,
            "No se puede aceptar: stock insuficiente de: " + "; ".join(faltantes)
        )
        return redirect("farmacia_pedidos")

    # 3) Aceptar + descontar stock + notificar
    with transaction.atomic():
        pedido.estado = "ACEPTADO"
        pedido.save()
        pedido.descontar_stock()


    messages.success(request, "Se aceptó el pedido exitosamente.")
    return redirect("farmacia_pedidos")

@login_required
def farmacia_rechazar(request, pedido_id):
    if not es_farmacia(request.user): 
        return HttpResponseForbidden("Solo farmacias")

    pedido = get_object_or_404(
        Pedido, 
        id=pedido_id, 
        estado="PENDIENTE", 
        farmacia=request.user.farmacia 
    )
    if request.method != "POST":
        messages.error(request, "Debes seleccionar un motivo para rechazar el pedido.")
        return redirect("farmacia_pedidos")

    motivo = request.POST.get("motivo")
    comentario = (request.POST.get("comentario") or "").strip()

    if not motivo:
        messages.error(request, "Seleccioná un motivo de rechazo.")
        return redirect("farmacia_pedidos")

    if motivo == "OTRO" and not comentario:
        messages.error(request, "Indicá un detalle cuando el motivo es 'Otro'.")
        return redirect("farmacia_pedidos")

    pedido.estado = "RECHAZADO"
    pedido.motivo_rechazo = motivo
    pedido.comentario_rechazo = comentario or None
    pedido.save()
    messages.success(request, f"Se rechazo el pedido exitosamente.")
    return redirect("farmacia_pedidos")

@login_required
def farmacia_gestionar_inventario(request):
    if not es_farmacia(request.user): 
        return HttpResponseForbidden("Solo farmacias")
    farmacia = request.user.farmacia
    stock_items = StockMedicamento.objects.filter(farmacia=farmacia).select_related('medicamento').order_by('medicamento__nombre_comercial')
    add_form = AddStockMedicamentoForm(farmacia=farmacia)
    edit_form = EditStockMedicamentoForm()
    if request.method == 'POST':
        # Procesar el formulario para AÑADIR un nuevo medicamento al stock
        add_form = AddStockMedicamentoForm(farmacia, request.POST)
        if add_form.is_valid():
            medicamento = add_form.cleaned_data['medicamento']
            precio = add_form.cleaned_data['precio']
            stock = add_form.cleaned_data['stock_actual']

            try:
                # Crear el nuevo registro de stock
                StockMedicamento.objects.create(
                    farmacia=farmacia,
                    medicamento=medicamento,
                    precio=precio,
                    stock_actual=stock
                )
                messages.success(request, f"Se agregó {medicamento.nombre_comercial} al inventario.")
                return redirect('gestionar_inventario') # Redirigir para limpiar el form
            except IntegrityError: # Por si acaso intenta agregar uno que ya existe (aunque el form lo evita)
                messages.error(request, f"{medicamento.nombre_comercial} ya existe en tu inventario.")
            except Exception as e:
                 messages.error(request, f"Ocurrió un error al agregar el medicamento: {e}")

        else:
            # Si el form de añadir no es válido, mostramos los errores
             messages.error(request, "Error al agregar el medicamento. Revisa los datos ingresados.")
             edit_form = EditStockMedicamentoForm() # Formulario vacío para editar (contexto)

    else:
        # Si es GET, mostramos un formulario vacío para añadir
        add_form = AddStockMedicamentoForm(farmacia=farmacia)
        edit_form = EditStockMedicamentoForm() # También para el contexto inicial

    context = {
        'stock_items': stock_items,
        'add_form': add_form,
        'edit_form': edit_form, # Usaremos este mismo form para editar en la misma página
    }
    return render(request, "orders/farmacia/inventario.html", context)

@login_required
def farmacia_editar_stock(request, stock_id):
    if not es_farmacia(request.user): 
        return HttpResponseForbidden("Solo farmacias")
    farmacia = request.user.farmacia
    stock_item = get_object_or_404(StockMedicamento, id=stock_id, farmacia=farmacia)

    if request.method == 'POST':
        edit_form = EditStockMedicamentoForm(request.POST, instance=stock_item)
        if edit_form.is_valid():
            edit_form.save()
            messages.success(request, f"Se actualizó el stock de {stock_item.medicamento.nombre_comercial}.")
        else:
            # Si hay errores en el form de edición, volvemos a mostrar la página de inventario
            # con los errores en el formulario de edición.
            messages.error(request, f"Error al actualizar {stock_item.medicamento.nombre_comercial}. Revisa los datos.")
            farmacia_actual = request.user.farmacia
            stock_items = StockMedicamento.objects.filter(farmacia=farmacia_actual).select_related('medicamento').order_by('medicamento__nombre_comercial')
            add_form = AddStockMedicamentoForm(farmacia=farmacia_actual) # Necesario para re-renderizar

            context = {
                'stock_items': stock_items,
                'add_form': add_form,
                'edit_form': edit_form, # Pasamos el form con errores
                'editing_item_id': stock_id # Para saber qué item se estaba editando
            }
            return render(request, 'orders/farmacia/inventario.html', context)

    # Si es GET, redirigimos a la página principal de inventario (la edición se hace in-place)
    return redirect('gestionar_inventario')

# ---------- REPARTIDOR ----------
@login_required
def repartidor_panel(request):
    if not es_repartidor(request.user): return HttpResponseForbidden("Solo repartidores")
    disponibles = Pedido.objects.filter(estado="ACEPTADO", repartidor__isnull=True)
    # Usar la instancia `Repartidor` asociada al user
    mis = Pedido.objects.filter(repartidor=request.user.repartidor).exclude(estado__in=["ENTREGADO"])

    repartidor_instance = Repartidor.objects.get(user=request.user)

    pedido_activo = Pedido.objects.filter(
        repartidor = repartidor_instance,
        estado = 'EN_CAMINO'
    ).first()

    return render(request, "orders/repartidor/panel.html", {"disponibles": disponibles, "mis": mis, "pedido_activo": pedido_activo})

@login_required
def repartidor_tomar(request, pedido_id):
    if not es_repartidor(request.user): return HttpResponseForbidden("Solo repartidores")
    p = get_object_or_404(Pedido, id=pedido_id, estado="ACEPTADO", repartidor__isnull=True)
    # asignar la instancia Repartidor relacionada al user, no el User
    p.repartidor = request.user.repartidor
    p.estado = "EN_CAMINO"
    p.save()
    return redirect("repartidor_panel")

@login_required
def repartidor_entregado(request, pedido_id):
    if not es_repartidor(request.user): return HttpResponseForbidden("Solo repartidores")
    p = get_object_or_404(Pedido, id=pedido_id, repartidor=request.user.repartidor, estado="EN_CAMINO")
    p.estado = "ENTREGADO"
    p.save()
    return redirect("repartidor_panel")

def repartidor_ver_pedidos(request):
    # chequeo instancia Repartidor
    if not es_repartidor(request.user): return HttpResponseForbidden("Solo repartidores")

    # se puede chequear aqui que no tenga un pedido en curso si se quiere.
    if Pedido.objects.filter(repartidor=request.user.repartidor, estado="EN_CAMINO").exists():
        messages.warning(request, "Tienes un pedido en curso.")
        return redirect("repartidor_panel")

    pedidos = Pedido.objects.filter(estado="ACEPTADO").order_by("creado")
    return render(request, "orders/repartidor/pedidos.html", {"pedidos": pedidos})

def repartidor_aceptar(request, pedido_id):
    if request.method!="POST":
        return redirect("repartidor_panel")
    if not es_repartidor(request.user):
        return HttpResponseForbidden("Solo repartidores")

    try:
        repartidor_instance = Repartidor.objects.get(user=request.user)
    except Repartidor.DoesNotExist:
    # Esto ocurre si el usuario pasa el es_repartidor pero el perfil no está creado
        messages.error(request, "Tu perfil de repartidor no está completo o no existe.")
        return redirect('repartidor_panel')

    if not repartidor_instance.disponible:
        messages.error(request, "Ya tienes un pedido asignado o en curso y no puedes aceptar uno nuevo.")
        return redirect("repartidor_panel")
    
    try:
        pedido = Pedido.objects.get(
            pk=pedido_id, 
            estado="ACEPTADO", 
            repartidor__isnull=True
        )
    except Pedido.DoesNotExist:
        # Captura si el pedido ya fue tomado o no cumple las condiciones
        messages.error(request, "Este pedido ya no está disponible.")
        return redirect("repartidor_panel")

    repartidor_instance.disponible = False
    repartidor_instance.save()

    pedido.repartidor = repartidor_instance
    pedido.estado = 'EN_CAMINO'        
    pedido.save()
    messages.success(request, f"Has aceptado el pedido #{pedido.id}.")
    return redirect("repartidor_panel")

@login_required
def repartidor_ver_pedido_actual(request):
    if not es_repartidor(request.user):
        return HttpResponseForbidden("Solo repartidores")
    try:
        repartidor_instance = Repartidor.objects.get(user=request.user)
    except Repartidor.DoesNotExist:
        messages.error(request, "Tu perfil de repartidor no está completo o no existe.")
        return redirect('repartidor_panel')
    try:
        pedido = Pedido.objects.get(
            repartidor=repartidor_instance,
            estado="EN_CAMINO"
        )
    except Pedido.DoesNotExist:
        messages.warning(request, "No tienes una entrega activa asignada. Vuelve al panel para tomar una.")
        return redirect('repartidor_panel')

    context = {
        'pedido': pedido,
        'repartidor': repartidor_instance,
        'origen':pedido.farmacia.direccion,
        'destino':pedido.direccion,
        'total':pedido.total,
        
    }

    return render(request, 'orders/repartidor/ver_pedido_actual.html', context)


@login_required
def repartidor_entregar_pedido(request, pedido_id):
    """Marca el pedido como ENTREGADO y libera al repartidor.

    Requisitos:
    - Solo POST
    - Usuario debe ser repartidor
    - El pedido debe estar asignado al repartidor y en estado EN_CAMINO
    """
    if request.method != 'POST':
        return redirect('repartidor_panel')

    if not es_repartidor(request.user):
        return HttpResponseForbidden("Solo repartidores")

    try:
        repartidor_instance = Repartidor.objects.get(user=request.user)
    except Repartidor.DoesNotExist:
        messages.error(request, "Tu perfil de repartidor no está completo o no existe.")
        return redirect('repartidor_panel')

    try:
        pedido = Pedido.objects.get(pk=pedido_id, repartidor=repartidor_instance, estado='EN_CAMINO')
    except Pedido.DoesNotExist:
        messages.error(request, "No tienes un pedido en curso con ese ID.")
        return redirect('repartidor_panel')

    # Marcar como entregado y liberar repartidor
    pedido.estado = 'ENTREGADO'
    pedido.save()

    repartidor_instance.disponible = True
    repartidor_instance.save()

    messages.success(request, f"Has marcado el pedido #{pedido.id} como entregado.")
    return redirect('repartidor_panel')



#---------------------pedido----------------


@login_required
def crear_pedido(request):
    form = PedidoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        p = form.save(commit=False)
        p.cliente = request.user
        p.save()
        return redirect("cliente_panel")
    return render(request, "orders/cliente/crearPedido.html", {"form": form})


#---------- Panel redirect ----------




