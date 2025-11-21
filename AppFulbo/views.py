from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
import AppFulbo.forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from .forms import LigaForm,PartidoForm,SimularPartidoForm,CrearYAsociarJugadorForm,AsociarUsuarioForm,JugadorForm  #,MensajeForm
from .models import Liga, Jugador,PuntajePartido,Partido, PuntuacionPendiente#,Mensaje,Conversacion
from django.contrib import messages
from django.db.models import Sum
import itertools
from django.contrib.auth.models import User
import itertools
from .models import Liga, Jugador

def inicio(request):
    return render(request,"AppFulbo/inicio.html") #como tercer argumento le tengo que pasar en forma de diccionario la info


def register(request):
    if request.method == 'POST':
        # 1. Usamos el formulario que acepta tanto datos como archivos (request.FILES)
        form = AppFulbo.forms.UserRegisterForm(request.POST, request.FILES)

        if form.is_valid():
            # 2. Guardamos el usuario. El perfil se crea automáticamente gracias a las señales.
            user = form.save()

            # 3. Guardamos los datos extra (foto y fecha) en el modelo Profile.
            user.profile.fecha_nacimiento = form.cleaned_data.get('fecha_nacimiento')
            if 'foto_perfil' in request.FILES:
                user.profile.foto_perfil = request.FILES['foto_perfil']
            user.profile.save()

            # 4. AÑADIMOS TU LÓGICA DE AUTO-LOGIN
            # Usamos la contraseña limpia del formulario para autenticar
            password = form.cleaned_data.get('password2')
            authenticated_user = authenticate(username=user.username, password=password)

            if authenticated_user is not None:
                login(request, authenticated_user)
                messages.success(request, f'¡Bienvenido, {user.username}! Tu cuenta ha sido creada.')
                # 5. Redirigimos a 'inicio', como querías.
                return redirect('inicio')
    else:
        form = AppFulbo.forms.UserRegisterForm()

    return render(request, "registro/register.html", {"formulario": form})

def login_request(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data = request.POST)

        if form.is_valid():  # Si pasó la validación de Django

            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')

            user = authenticate(username= username, password=password)

            if user is not None:
                login(request, user)
                return redirect('inicio')
            else:
                return render(request, "registro/login.html", {"mensaje":"Datos incorrectos"})
           
        else:
            formulario = AuthenticationForm()
            return render(request, "registro/login.html", {"mensaje":"Datos incorrectos","formulario": formulario})

    formulario = AuthenticationForm()

    return render(request, "registro/login.html", {"formulario": formulario})

@login_required
def custom_logout(request):
    logout(request)
    return redirect('inicio')

#editar usuario

@login_required
def edit_profile(request):
    usuario = request.user
    perfil = usuario.profile

    if request.method == 'POST':
        form = AppFulbo.forms.UserEditForm(request.POST, request.FILES, instance=usuario, profile_instance=perfil)
        if form.is_valid():
            form.save(user_instance=usuario, profile_instance=perfil)
            return redirect('mi_perfil')
    else:
        form = AppFulbo.forms.UserEditForm(instance=usuario, profile_instance=perfil)

    return render(request, 'registro/edit_profile.html', {'form': form})


@login_required
def mis_ligas(request):
    # Obtenemos todos los registros de Jugador asociados al usuario logueado.
    jugadores = Jugador.objects.filter(usuario=request.user)
    # Para cada jugador, obtenemos la liga y le asignamos un atributo 'mi_jugador'
    # que luego se usará en la plantilla.
    ligas_con_jugador = []
    for jugador in jugadores:
        liga = jugador.liga
        liga.mi_jugador = jugador  # Agregamos el jugador a la instancia de liga
        ligas_con_jugador.append(liga)
    
    context = {
        'ligas': ligas_con_jugador
    }
    return render(request, 'AppFulbo/mis_ligas.html', context)



# @login_required
# def buscar_ligas(request):
#     if request.method == 'POST':
#         liga_id = request.POST.get('liga_id')
#         #ligas = Liga.objects.all()
#         #liga_elegida = ligas.get(id=liga_id)
#         liga_elegida = get_object_or_404(Liga, id=liga_id)
#         #aca creo la solicitud
#         mi_jugador = liga_elegida.jugadores.filter(usuario=request.user).first()
#         if mi_jugador:
#             messages.success(request, f"Ya estas en esta liga.")
#         else:
            
#             if not SolicitudUnionLiga.objects.filter(usuario=request.user, liga=liga_elegida).exists():
#                 SolicitudUnionLiga.objects.create(usuario=request.user, liga=liga_elegida)
#                 messages.success(request, "Solicitud enviada.")
#             else:
#                 messages.info(request, "Ya has solicitado unirte a esta liga.")
#         return redirect('ver_liga', liga_id=liga_elegida.id)
#     else:
#         query = request.GET.get('q', '')
#         if query:
#             ligas = Liga.objects.filter(nombre_liga__icontains=query)
#         else:
#             ligas = Liga.objects.all()
        
#         context = {
#             'ligas': ligas,
#             'query': query,
#         }
#         return render(request, 'AppFulbo/buscar_ligas.html', context)
            
    
# @login_required
# def elegir_o_crear_jugador(request, liga_id):
#     liga = get_object_or_404(Liga, id=liga_id)
    
#     # Verificar si el usuario ya tiene un jugador en esta liga
#     if Jugador.objects.filter(usuario=request.user, liga=liga).exists():
#         messages.info(request, f"Ya te has unido a la liga {liga.nombre}.")
#         return redirect('AppFulbo/mis_ligas')
    
#     if request.method == "POST":
#         # Si el usuario eligió un jugador existente
#         if 'jugador_id' in request.POST:
#             jugador_id = request.POST.get('jugador_id')
#             jugador = get_object_or_404(Jugador, id=jugador_id, liga=liga, usuario__isnull=True)
#             jugador.usuario = request.user
#             jugador.save()
#             messages.success(request, f"Te has unido a la liga {liga.nombre} asignándote el jugador {jugador.nombre}.")
#             return redirect('mis_ligas')
#         # Si el usuario decide crear un nuevo jugador
#         elif 'crear_nuevo' in request.POST:
#             return redirect('AppFulbo/crear_jugador', liga_id=liga.id)
    
#     # Si es una solicitud GET, mostrar la lista de jugadores pre-creados disponibles
#     jugadores_disponibles = Jugador.objects.filter(liga=liga, usuario__isnull=True)
#     context = {
#         "liga": liga,
#         "jugadores_disponibles": jugadores_disponibles,
#     }
#     return render(request, "AppFulbo/elegir_jugador.html", context)




@login_required
def partidos_jugados(request):
    # Filtramos todos los registros de PuntajePartido de los jugadores del usuario
    puntajes = PuntajePartido.objects.filter(
        jugador__usuario=request.user
    ).select_related('partido', 'partido__liga', 'jugador').order_by('-partido__fecha_partido')
    
    context = {
        'puntajes': puntajes,
    }
    return render(request, 'AppFulbo/mis_partidos.html', context)

@login_required
def mi_perfil(request):
    user = request.user
    # Se filtran los jugadores del usuario y se anota el puntaje total (suma de puntajes en cada partido)
    jugadores = Jugador.objects.filter(usuario=user).annotate(total_puntaje=Sum('puntajes_partidos__puntaje'))
    
    context = {
        'user': user,
        'jugadores': jugadores,
    }
    return render(request, 'AppFulbo/mi_perfil.html', context)

@login_required
def crear_liga(request):
    if request.method == 'POST':
        form_liga = LigaForm(request.POST)
        form_jugador = JugadorForm(request.POST)  # ya no necesitamos pasar el usuario para filtrar la liga
        if form_liga.is_valid() and form_jugador.is_valid():
            nueva_liga = form_liga.save()
            nuevo_jugador = form_jugador.save(commit=False)
            nuevo_jugador.usuario = request.user
            nuevo_jugador.liga = nueva_liga  # Asigna manualmente la liga recién creada
            nuevo_jugador.save()
            nueva_liga.presidentes.add(request.user)            
            nueva_liga.super_presidente = request.user
            nueva_liga.save()

            messages.success(request, "Liga y jugador creados exitosamente.")
            return redirect('ver_liga', liga_id=nueva_liga.id)
    else:
        context = {
            'form_liga' : LigaForm(),
            'form_jugador' : JugadorForm(),  
        }

    return render(request, 'registro/crear_liga.html', context)

@login_required
def ver_liga(request, liga_id):
    liga = get_object_or_404(Liga, id=liga_id)
    mi_jugador = None
    

    if request.user.is_authenticated:
        mi_jugador = liga.jugadores.filter(usuario=request.user).first()
        if mi_jugador is None: # Usar 'is None' es la forma idiomática en Python
            messages.error(request, f'No tienes un perfil de jugador asociado a esta liga privada. Por favor, contacta al presidente de la liga.')
            return redirect('inicio')  
            
    partidos = liga.partidos.all().order_by('-fecha_partido')
    puntuaciones_pendientes = mi_jugador.puntuaciones_jugador.filter(liga=liga) if mi_jugador else None


    context = {
        'liga': liga,
        'mi_jugador': mi_jugador,
        'partidos': partidos,
        'puntuaciones_pendientes': puntuaciones_pendientes,
        'zero':0
    }
    return render(request, 'AppFulbo/ver_liga.html', context)


@login_required
def editar_liga(request, liga_id):
    liga = get_object_or_404(Liga, id=liga_id)
    # Obtén las relaciones
    presidentes = liga.presidentes.all()
    if not (request.user == liga.super_presidente or request.user in presidentes.all()):
        messages.error(request, f'No tiene permiso para editar la liga.')
        return redirect('ver_liga.html',liga_id) 
    
    jugadores = liga.jugadores.filter(activo=True)
    partidos = liga.partidos.all()

    if request.method == "POST":
        action = request.POST.get('action')
        # Acciones posibles:
        if action == "asociar_jugador":
            jugador_id = request.POST.get('jugador_id')
            return redirect('agregar_jugador_a_liga', liga_id=liga.id,jugador_id=jugador_id)
        elif action == "editar_liga":
            form = LigaForm(request.POST, instance=liga)
            if form.is_valid():
                form.save()
                messages.success(request, "Datos de la liga actualizados.")
            else:
                messages.error(request, "Error al actualizar la liga.")
        elif action == "add_president":
            presidente_id = request.POST.get('presidente_id')
            # Verifica que el usuario sea el super_presidente
            if request.user != liga.super_presidente:
                messages.error(request, "Solo el SuperPresidente puede eliminar a los presidentes.")
            else:
                # Supongamos que el formulario trae el username del nuevo presidente.
                nuevo_username = request.POST.get('nuevo_presidente')
                # Aquí deberías buscar al usuario y agregarlo:
                from django.contrib.auth.models import User
                try:
                    nuevo_presidente = User.objects.get(username=nuevo_username)
                    liga.presidentes.add(nuevo_presidente)
                    messages.success(request, f"{nuevo_username} agregado como presidente.")
                except User.DoesNotExist:
                    messages.error(request, "El usuario no existe.")
        elif action == "delete_president":
            presidente_id = request.POST.get('presidente_id')
            # Verifica que el usuario sea el super_presidente
            if request.user != liga.super_presidente:
                messages.error(request, "Solo el SuperPresidente puede eliminar a los presidentes.")
            else:
                try:
                    presidente = liga.presidentes.get(id=presidente_id)
                    liga.presidentes.remove(presidente)
                    messages.success(request, "Presidente eliminado.")
                except Exception as e:
                    messages.error(request, "Error al eliminar presidente.")
                    
        elif action == "edit_player":
            jugador_id = request.POST.get('jugador_id')
            return redirect('editar_jugador', jugador_id=jugador_id)
        
        elif action == "abandonar_liga":
            # Verifica si el usuario es el super_presidente
            if request.user == liga.super_presidente:
                messages.error(request, "Debes asignar a un superpresidente antes de irte.")
            else:
                # Elimina al usuario de la lista de presidentes
                liga.presidentes.remove(request.user)
                # Buscar el jugador asociado al usuario en esta liga y marcarlo como inactivo.
                jugador = liga.jugadores.filter(usuario=request.user, activo=True).first()
                if jugador:
                    jugador.activo = False
                    jugador.save()
                messages.success(request, "Has abandonado la liga y tu jugador ha sido desactivado.")
                return redirect('ver_liga', liga_id=liga.id)
            
        elif action == "delete_player":
            jugador_id = request.POST.get('jugador_id')
            try:
                jugador = Jugador.objects.get(id=jugador_id)
                jugador.delete()
                messages.success(request, "Jugador eliminado.")
            except Exception as e:
                messages.error(request, "Error al eliminar jugador.")
        elif action == "edit_match":
            # Lógica para editar partido
            partido_id = request.POST.get('partido_id')
            messages.info(request, f"Editar partido {partido_id}.")
        elif action == "delete_match":
            partido_id = request.POST.get('partido_id')
            try:
                partido = Partido.objects.get(id=partido_id)
                partido.delete()
                messages.success(request, "Partido eliminado.")
            except Exception as e:
                messages.error(request, "Error al eliminar partido.")
        
        elif action == "hacer_super_presidente":
            # Verificar que el usuario que realiza la acción sea el superpresidente actual
            if request.user != liga.super_presidente:
                messages.error(request, "Solo el superpresidente actual puede realizar este cambio.")
            else:
                nuevo_super_id = request.POST.get('presidente_id')
                try:
                    nuevo_super = liga.presidentes.get(id=nuevo_super_id)
                except liga.presidentes.model.DoesNotExist:
                    nuevo_super = None

                if not nuevo_super:
                    messages.error(request, "El presidente elegido no existe o no es válido.")
                else:
                    # Verificamos que el usuario elegido ya sea presidente
                    if nuevo_super not in liga.presidentes.all():
                        messages.error(request, "El usuario elegido debe ser presidente antes de ser designado como superpresidente.")
                    else:
                        # Asignamos el nuevo superpresidente y guardamos
                        liga.super_presidente = nuevo_super
                        liga.save()
                        messages.success(request, f"{nuevo_super.username} ahora es el superpresidente de la liga.")
            return redirect('editar_liga', liga_id=liga.id)


        # Después de la acción, redirige a la misma vista para refrescar la información.
        return redirect('editar_liga', liga_id=liga.id)

    else:
        # Para editar datos de la liga, inicializamos un formulario:
        form = LigaForm(instance=liga)

    context = {
        'liga': liga,
        'form': form,
        'presidentes': presidentes,
        'jugadores': jugadores,
        'partidos': partidos,
    }
    return render(request, 'AppFulbo/editar_liga.html', context)

    
def verificar_usuario_ajax(request):
    username = request.GET.get('username', '')
    liga_id = request.GET.get('liga_id')

    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        return JsonResponse({'exists': False})

    # Verificar si ya tiene un jugador en esa liga
    if liga_id:
        try:
            liga = Liga.objects.get(id=liga_id)
            if Jugador.objects.filter(usuario=user, liga=liga).exists():
                return JsonResponse({'exists': False})  # ya tiene jugador en esta liga
        except Liga.DoesNotExist:
            return JsonResponse({'exists': False})

    return JsonResponse({
        'exists': True,
        'first_name': user.first_name,
        'last_name': user.last_name
    })


@login_required
def gestionar_jugadores_liga(request, liga_id):
    liga = get_object_or_404(Liga, id=liga_id)

    # solo los presidentes de la liga pueden gestionar jugadores
    if not (request.user == liga.super_presidente or request.user in liga.presidentes.all()):
        messages.error(request, "No tienes permiso para gestionar jugadores en esta liga.")
        return redirect('ver_liga', liga_id=liga_id)

    jugadores_activos = Jugador.objects.filter(liga=liga, activo=True).order_by('apodo')
    jugadores_inactivos = Jugador.objects.filter(liga=liga, activo=False).order_by('apodo')
    context = {
        'liga': liga,
        'jugadores_activos': jugadores_activos,
        'jugadores_inactivos': jugadores_inactivos,
    }
    return render(request, 'AppFulbo/gestionar_jugadores.html', context)


@login_required
def agregar_jugador_y_usuario(request, liga_id): 
    liga = get_object_or_404(Liga, id=liga_id)

    if not (request.user == liga.super_presidente or request.user in liga.presidentes.all()):
        messages.error(request, "No tienes permiso para agregar jugadores a esta liga.")
        return redirect('ver_liga', liga_id=liga_id)

    if request.method == 'POST':
        form = CrearYAsociarJugadorForm(request.POST, liga=liga)
        if form.is_valid():
            # Ahora username_usuario en cleaned_data ya es el objeto User
            usuario_a_asociar = form.cleaned_data['username_usuario'] 
            apodo = form.cleaned_data['apodo']
            posicion = form.cleaned_data['posicion']
            numero = form.cleaned_data['numero']
            
            Jugador.objects.create(
                usuario=usuario_a_asociar,
                liga=liga,
                apodo=apodo,
                posicion=posicion,
                numero=numero,
                activo=True
            )
            messages.success(request, f"El jugador '{apodo}' ha sido creado y asociado a '{usuario_a_asociar.username}'.")
            return redirect('gestionar_jugadores_liga', liga_id=liga_id)
        else:
            # Si el formulario no es válido, los errores se mostrarán automáticamente
            # en la plantilla gracias al renderizado manual y Crispy.
            # No necesitamos un 'messages.error' general aquí a menos que quieras algo extra.
            pass 
    else:
        form = CrearYAsociarJugadorForm(liga=liga)

    context = {
        'form': form,
        'liga': liga,
        'titulo': "Agregar Nuevo Jugador y Asociar Usuario"
    }
    return render(request, 'AppFulbo/agregar_jugador_y_usuario_form.html', context)

# ... (resto de tus vistas) ...

@login_required 
def agregar_jugador(request, liga_id):
    liga = get_object_or_404(Liga, id=liga_id)

    if not (request.user == liga.super_presidente or request.user in liga.presidentes.all()):
        messages.error(request, "No tienes permiso para agregar jugadores a esta liga.")
        return redirect('ver_liga', liga_id=liga.id)

    if request.method == 'POST':
        form = JugadorForm(request.POST, liga=liga)
        if form.is_valid():
            jugador = form.save(commit=False)
            jugador.liga = liga
            jugador.save()

            action = request.POST.get('action') 

            if action == 'crear_y_asociar':
                messages.success(request, f"El jugador '{jugador.apodo}' ha sido creado exitosamente. Ahora asocia un usuario.")
                # Redirigir a TU vista de asociación, pasando el ID del jugador
                return redirect('asociar_usuario_a_jugador', liga_id=liga.id, jugador_id=jugador.id) # <--- ¡CAMBIO AQUÍ!
            else: # action == 'crear' o cualquier otra cosa (por defecto)
                messages.success(request, f"El jugador '{jugador.apodo}' ha sido creado exitosamente en la liga '{liga.nombre_liga}'.") 
                return redirect('gestionar_jugadores_liga', liga_id=liga.id)
        else:
            pass # Si el formulario no es válido, se renderiza de nuevo con los errores
    else:
        form = JugadorForm(liga=liga)

    context = {
        'form': form,
        'liga': liga,
        'titulo': "Agregar Nuevo Jugador" 
    }
    return render(request, 'AppFulbo/jugador_form.html', context)


@login_required
def modificar_jugador(request, liga_id, jugador_id):
    liga = get_object_or_404(Liga, id=liga_id)
    jugador = get_object_or_404(Jugador, id=jugador_id, liga=liga)

    if not (request.user == liga.super_presidente or request.user in liga.presidentes.all()):
        messages.error(request, "No tienes permiso para modificar jugadores en esta liga.")
        return redirect('ver_liga', liga_id=liga_id)

    if request.method == 'POST':
        # instancia del jugador y la liga al formulario
        form = JugadorForm(request.POST, instance=jugador, liga=liga)
        if form.is_valid():
            form.save() # Guarda los cambios en la instancia del jugador
            messages.success(request, f"Jugador '{jugador.apodo}' modificado correctamente.")
            return redirect('gestionar_jugadores_liga', liga_id=liga_id)
    else:
        # formulario con los datos actuales del jugador
        form = JugadorForm(instance=jugador, liga=liga)

    context = {
        'form': form,
        'liga': liga,
        'jugador': jugador, # Pasamos el objeto jugador para que la plantilla sepa que es una modificación
        'titulo': f"Modificar Jugador: {jugador.apodo}"
    }
    return render(request, 'AppFulbo/jugador_form.html', context) # <--- ¡Usamos la misma plantilla!

@login_required
def asociar_usuario_a_jugador(request, liga_id, jugador_id):
    liga = get_object_or_404(Liga, id=liga_id)
    jugador = get_object_or_404(Jugador, id=jugador_id, liga=liga)

    if not (request.user == liga.super_presidente or request.user in liga.presidentes.all()):
        messages.error(request, "No tienes permiso para asociar usuarios a jugadores en esta liga.")
        return redirect('ver_liga', liga_id=liga_id)
    
    # Validar que el jugador realmente no tenga un usuario asociado
    if jugador.usuario is not None:
        messages.warning(request, f"El jugador '{jugador.apodo}' ya está asociado al usuario '{jugador.usuario.username}'.")
        return redirect('gestionar_jugadores_liga', liga_id=liga_id)

    if request.method == 'POST':
        # Pasamos la liga y el jugador al formulario para validaciones
        form = AsociarUsuarioForm(request.POST, liga=liga, jugador_a_asociar=jugador)
        if form.is_valid():
            username = form.cleaned_data['username_usuario']
            usuario_a_asociar = User.objects.get(username=username) # Ya validado por el formulario
            
            jugador.usuario = usuario_a_asociar
            jugador.save()
            messages.success(request, f"¡El jugador '{jugador.apodo}' ha sido asociado al usuario '{usuario_a_asociar.username}'!")
            return redirect('gestionar_jugadores_liga', liga_id=liga_id)
    else:
        form = AsociarUsuarioForm(liga=liga, jugador_a_asociar=jugador)

    context = {
        'form': form,
        'liga': liga,
        'jugador': jugador,
        'titulo': f"Asociar Usuario a {jugador.apodo}"
    }
    return render(request, 'AppFulbo/asociar_usuario_form.html', context) # Necesitarás crear esta plantilla

@login_required
def eliminar_jugador(request, liga_id, jugador_id):
    liga = get_object_or_404(Liga, id=liga_id)
    jugador = get_object_or_404(Jugador, id=jugador_id, liga=liga)

    # Verifica si el usuario tiene permisos para desactivar jugadores en esta liga
    if not (request.user == liga.super_presidente or request.user in liga.presidentes.all()):
        messages.error(request, "No tienes permiso para desactivar jugadores de esta liga.")
        return redirect('ver_liga', liga_id=liga_id)

    if request.method == 'POST':
        # Implementación del Soft Delete:
        # En lugar de eliminar el objeto de la base de datos,
        # simplemente marcamos el campo 'activo' como False.
        jugador.activo = False
        jugador.save()
        messages.success(request, f"Jugador '{jugador.apodo}' ha sido **desactivado** de la liga.")
        return redirect('gestionar_jugadores_liga', liga_id=liga_id)

    # Si la petición es GET, se muestra la página de confirmación
    context = {
        'liga': liga,
        'jugador': jugador
    }
    # La plantilla 'confirmar_eliminar_jugador.html' debe reflejar que es una desactivación.
    return render(request, 'AppFulbo/confirmar_eliminar_jugador.html', context)


@login_required
def reactivar_jugador(request, liga_id, jugador_id):
    liga = get_object_or_404(Liga, id=liga_id)
    jugador = get_object_or_404(Jugador, id=jugador_id, liga=liga)

    # Permisos: Solo super_presidente o presidentes pueden reactivar
    if not (request.user == liga.super_presidente or request.user in liga.presidentes.all()):
        messages.error(request, "No tienes permiso para reactivar jugadores en esta liga.")
        return redirect('gestionar_jugadores_liga', liga_id=liga_id)

    if request.method == 'POST':
        jugador.activo = True  # Marca el jugador como activo
        jugador.save()
        messages.success(request, f"Jugador '{jugador.apodo}' ha sido reactivado en la liga.")
        return redirect('gestionar_jugadores_liga', liga_id=liga_id)

    # Si se accede por GET, mostrar una página de confirmación (opcional, pero buena práctica)
    context = {
        'liga': liga,
        'jugador': jugador
    }
    # Podrías reutilizar 'confirmar_eliminar_jugador.html' adaptando el texto,
    # o crear una nueva como 'confirmar_reactivar_jugador.html'
    return render(request, 'AppFulbo/confirmar_reactivar_jugador.html', context)
     

@login_required
def encontrar_equipos_mas_parejos(request, liga_id):
    liga = get_object_or_404(Liga, id=liga_id)
    
    if request.method == 'POST':
        jugadores_seleccionados_ids = request.POST.getlist('jugadores') # IDs de los jugadores seleccionados
        
        # Filtrar solo jugadores activos y con puntaje no nulo para evitar errores
        jugadores = list(Jugador.objects.filter(
            id__in=jugadores_seleccionados_ids,
            liga=liga,
            activo=True,
            puntaje__isnull=False # Asegúrate de que el puntaje no sea Nulo
        ).order_by('-puntaje')) # Opcional: ordenar para facilitar la depuración, no es estrictamente necesario para el algoritmo de combinaciones.

        if not jugadores:
            # Manejar caso donde no hay jugadores válidos seleccionados
            context = {
                'liga': liga,
                'error_message': "No se seleccionaron jugadores válidos o con puntaje para armar los equipos.",
            }
            return render(request, 'AppFulbo/crear_equipos.html', context)
        
        num_jugadores = len(jugadores)
        
        # Si el número de jugadores es impar, un equipo tendrá un jugador más.
        # Definimos el tamaño del primer equipo (aproximadamente la mitad)
        tamano_equipo1 = num_jugadores // 2
        
        mejor_equipo1 = []
        mejor_equipo2 = []
        min_diferencia_puntaje = float('inf')

        # Si hay menos de 2 jugadores, no se pueden formar equipos
        if num_jugadores < 2:
            context = {
                'liga': liga,
                'error_message': "Se necesitan al menos 2 jugadores para formar equipos.",
            }
            return render(request, 'AppFulbo/crear_equipos.html', context)
            
        # Itera sobre todas las combinaciones posibles para el Equipo 1
        # El segundo equipo será el complemento del primero
        # Consideramos combinaciones que pueden variar ligeramente si el número de jugadores es impar
        for combo in itertools.combinations(jugadores, tamano_equipo1):
            equipo1_lista = list(combo)
            equipo2_lista = [j for j in jugadores if j not in equipo1_lista]

            # Si el número total de jugadores es impar, ajustamos el tamaño del equipo 1
            # para que la división sea lo más pareja posible
            if num_jugadores % 2 != 0:
                # Nos aseguramos de que el equipo 2 tenga un jugador más si el equipo 1 tiene menos de la mitad
                # o el equipo 1 tenga uno más si tamano_equipo1 es la mitad superior
                # La iteración de itertools ya maneja esto implícitamente al tomar tamano_equipo1
                pass # No se necesita ajuste explícito aquí si itertools.combinations se usa correctamente.
            
            # Calcular puntajes totales
            suma_equipo1 = sum(j.puntaje for j in equipo1_lista)
            suma_equipo2 = sum(j.puntaje for j in equipo2_lista)
            
            diferencia_actual = abs(suma_equipo1 - suma_equipo2)
            
            if diferencia_actual < min_diferencia_puntaje:
                min_diferencia_puntaje = diferencia_actual
                mejor_equipo1 = equipo1_lista
                mejor_equipo2 = equipo2_lista

        context = {
            'liga': liga,
            'equipo1': mejor_equipo1,
            'equipo2': mejor_equipo2,
            'suma_equipo1': sum(j.puntaje for j in mejor_equipo1),
            'suma_equipo2': sum(j.puntaje for j in mejor_equipo2),
            'diferencia': min_diferencia_puntaje,
        }
        return render(request, 'AppFulbo/equipos_resultado.html', context)

    else:
        # Aquí puedes obtener todos los jugadores de la liga o solo los activos
        # para mostrarlos en el formulario de selección.
        # Es bueno pre-seleccionar a los activos si quieres que el usuario parta de ahí.
        
        # Asegúrate de que SimularPartidoForm esté configurado para mostrar los jugadores disponibles.
        form = SimularPartidoForm(league=liga) 
        
        context = {
            'liga': liga,
            'form': form,
            'jugadores_disponibles': liga.jugadores.filter(activo=True, puntaje__isnull=False).order_by('apodo'),
        }
        return render(request, 'AppFulbo/crear_equipos.html', context)


    
def crear_partido(request, liga_id):
    league = get_object_or_404(Liga, id=liga_id)
    
    # Permisos para crear partido
    if not (request.user == league.super_presidente or request.user in league.presidentes.all()):
        messages.error(request, "No tienes permiso para crear partidos en esta liga.")
        return redirect('ver_liga', liga_id=league.id)

    if request.method == 'POST':
        # Pasamos 'league' SIEMPRE al formulario.
        form = PartidoForm(request.POST, league=league) # <--- Asegúrate de que 'league' se pase aquí
        if form.is_valid():
            partido = form.save(commit=False)
            partido.liga = league
            partido.save()
            
            jugadores_seleccionados = form.cleaned_data.get('jugadores')
            if jugadores_seleccionados:
                for jugador in jugadores_seleccionados:
                    PuntajePartido.objects.create(
                        jugador=jugador,
                        partido=partido,
                        puntaje=0.0
                    )
            
            messages.success(request, "Partido creado exitosamente.")
            return redirect('gestionar_partidos_liga', liga_id=league.id)
    else:
        # Pasamos 'league' SIEMPRE al formulario.
        form = PartidoForm(league=league) # <--- Asegúrate de que 'league' se pase aquí
    
    return render(request, 'AppFulbo/partido_form.html', {'form': form, 'liga': league, 'titulo': "Crear Nuevo Partido"})

@login_required
def puntuar_jugadores_partido(request, partido_id, puntuacion_pendiente_id):
    partido = get_object_or_404(Partido, id=partido_id)
    puntuacion_pendiente = get_object_or_404(PuntuacionPendiente, id=puntuacion_pendiente_id)


    if puntuacion_pendiente.partido != partido:
        return redirect('ver_partido', partido_id=partido.id)

    puntajes_partidos = partido.puntajes_partidos.all()
    jugadores = [puntaje.jugador for puntaje in puntajes_partidos]
    mi_jugador = next((jugador for jugador in jugadores if jugador.usuario == request.user), None)

    if mi_jugador and mi_jugador.puntuaciones_jugador:
        if request.method == "POST":
            for puntaje_partido in puntajes_partidos:
                jugador = puntaje_partido.jugador
                if jugador.usuario != request.user:  # Verifica que tenga usuario y no sea el actual
                    puntaje = request.POST.get(f'puntaje_{jugador.id}')
                    if puntaje:  # Verifica que se haya ingresado un puntaje
                        puntaje_partido.agregar_puntaje(float(puntaje))
                        puntaje_partido.save()
                        jugador.actualizar_puntaje()
                        jugador.save()

            # Borra la puntuación pendiente solo si coincide con el partido actual
            puntuacion_pendiente.delete()

            return redirect('ver_partido', partido_id=partido.id)
        else:
            jugadores.remove(mi_jugador)
            context = {
                'partido': partido,
                'jugadores': jugadores,
                'puntuacion_pendiente': puntuacion_pendiente
            }

            return render(request, 'AppFulbo/puntuar_jugadores.html', context)
    else:
        return redirect('ver_partido', partido_id=partido.id)


@login_required
def ver_partido(request, partido_id):
    partido = get_object_or_404(Partido, id=partido_id)
    puntajes = partido.puntajes_partidos.select_related('jugador').all()
    mi_jugador = None
    if request.user.is_authenticated:
        mi_jugador = Jugador.objects.filter(usuario=request.user, liga=partido.liga).first()
    puntuacion_pendiente = None
    if mi_jugador:
        puntuacion_pendiente = partido.puntuaciones_pendientes.filter(jugador_id=mi_jugador.id).first()

    context = {
        'partido': partido,
        'puntajes': puntajes,
        'puntuacion_pendiente': puntuacion_pendiente,  # ahora es un objeto, no un QuerySet
    }
    return render(request, 'AppFulbo/ver_partido.html', context)

@login_required
def gestionar_partidos_liga(request, liga_id):
    liga = get_object_or_404(Liga, id=liga_id)

    # Permisos: Solo super_presidente o presidentes de la liga pueden gestionar partidos
    if not (request.user == liga.super_presidente or request.user in liga.presidentes.all()):
        messages.error(request, "No tienes permiso para gestionar partidos en esta liga.")
        return redirect('ver_liga', liga_id=liga_id)

    # Usamos select_related para traer la info de liga en una sola consulta
    # y prefetch_related para traer los puntajes_partidos (y sus jugadores) eficientemente
    partidos = Partido.objects.filter(liga=liga).order_by('-fecha_partido').prefetch_related('puntajes_partidos__jugador')

    context = {
        'liga': liga,
        'partidos': partidos,
        'titulo': f"Gestión de Partidos en {liga.nombre_liga}"
    }
    return render(request, 'AppFulbo/gestionar_partidos.html', context) # <--- Nueva plantilla


# AppFulbo/views.p

# ... (Tus vistas existentes, como agregar_jugador, gestionar_jugadores_liga, gestionar_partidos_liga, etc.) ...

def modificar_partido(request, liga_id, partido_id):
    liga = get_object_or_404(Liga, id=liga_id)
    partido = get_object_or_404(Partido, id=partido_id, liga=liga)

    # Permisos: Solo super_presidente o presidentes de la liga pueden modificar partidos
    if not (request.user == liga.super_presidente or request.user in liga.presidentes.all()):
        messages.error(request, "No tienes permiso para modificar partidos en esta liga.")
        return redirect('gestionar_partidos_liga', liga_id=liga.id)

    if request.method == 'POST':
        # Instancia del partido y la liga al formulario. No pasamos 'initial' para jugadores
        # porque el campo 'jugadores' ya no existirá en el formulario de modificación.
        form = PartidoForm(request.POST, instance=partido, league=liga) 
        if form.is_valid():
            partido = form.save() # Guarda el partido (fecha y cancha)
            # NO hay manejo de PuntajePartido aquí, ya que no se modifican los jugadores
            messages.success(request, f"Partido del {partido.fecha_partido.strftime('%d/%m/%Y')} modificado correctamente.")
            return redirect('gestionar_partidos_liga', liga_id=liga.id)
    else:
        # Al cargar el formulario por primera vez, se inicializa con la instancia del partido.
        # El campo 'jugadores' no se agregará al formulario porque hay una instancia.
        form = PartidoForm(instance=partido, league=liga) 

    context = {
        'form': form,
        'liga': liga,
        'partido': partido, # Pasa la instancia de partido para que la plantilla sepa que es una edición
        'titulo': f"Modificar Partido: {partido.fecha_partido.strftime('%d/%m/%Y')}"
    }
    return render(request, 'AppFulbo/partido_form.html', context)

@login_required
def eliminar_partido(request, liga_id, partido_id):
    liga = get_object_or_404(Liga, id=liga_id)
    partido = get_object_or_404(Partido, id=partido_id, liga=liga)

    # Permisos: Solo super_presidente o presidentes de la liga pueden eliminar partidos
    if not (request.user == liga.super_presidente or request.user in liga.presidentes.all()):
        messages.error(request, "No tienes permiso para eliminar partidos en esta liga.")
        return redirect('gestionar_partidos_liga', liga_id=liga.id)

    if request.method == 'POST':
        partido_fecha = partido.fecha_partido.strftime('%d/%m/%Y')
        partido.delete()
        messages.success(request, f"Partido del {partido_fecha} eliminado correctamente.")
        return redirect('gestionar_partidos_liga', liga_id=liga.id)
    
    # Para mostrar una página de confirmación antes de eliminar (opcional)
    context = {
        'liga': liga,
        'partido': partido,
        'titulo': f"Confirmar Eliminación de Partido: {partido.fecha_partido.strftime('%d/%m/%Y')}"
    }
    return render(request, 'AppFulbo/confirmar_eliminar_partido.html', context) # <--- Nueva plantilla de confirmación

@login_required
def marcar_todas_notificaciones_ajax(request):
    if request.method == "POST":
        request.user.notificaciones.filter(leido=False).update(leido=True)
        return JsonResponse({'success': True})
    else:
        return JsonResponse({'error': 'Invalid request'}, status=400)


