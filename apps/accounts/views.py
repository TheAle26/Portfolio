from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth import login, logout
from .forms import (RegistroClienteForm, RegistroFarmaciaForm, RegistroRepartidorForm)
from .models import Cliente, Farmacia, Repartidor
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from apps.orders.utils import es_cliente, es_farmacia, es_repartidor
from django.http import HttpResponseForbidden


class CustomLoginView(LoginView):
    success_url = None
    template_name = "accounts/login.html" 
    #redirect_authenticated_user = True 

    def get_success_url(self):
        user = self.request.user
        # Si el usuario tiene permisos de staff o es superuser, redirige al admin
        if getattr(user, 'is_superuser'):
            return reverse('admin:index')
        
        elif hasattr(user, 'cliente'):
            return redirect("cliente_panel").url
        
        elif hasattr(user, 'farmacia'):
            farmacia = user.farmacia  
            if farmacia.valido:
                return redirect("farmacia_panel").url
            else:
                logout(self.request) 
                messages.error(self.request, "¡Acceso denegado! Tu perfil de Farmacia aún no ha sido validado por el administrador.")
                return redirect("login").url 
        
        
        elif hasattr(user, 'repartidor'):
            repartidor = user.repartidor 
            if repartidor.valido:
                return redirect("repartidor_panel").url
            else:
                logout(self.request) 
                messages.error(self.request, "¡Acceso denegado! Tu perfil de Repartidor aún no ha sido validado por el administrador.")
                return redirect("login").url
        
        
        # 4. DEFAULT
        return super().get_success_url()
   
login_view = CustomLoginView.as_view()
logout_view = LogoutView.as_view()

def logout_view(request):
    logout(request)
    messages.info(request, "Has cerrado sesión.")
    return redirect("FarmaGohome")

def registro_selector(request):
    return render(request, "accounts/registro_selector.html")

def tyc(request):
    return render(request, "accounts/tyc.html")

def registro_cliente(request):
    form = RegistroClienteForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()  # crea User (email + pass)
        Cliente.objects.create(
            user=user,
            nombre=form.cleaned_data["nombre"],
            apellido=form.cleaned_data["apellido"],
            documento=form.cleaned_data["documento"], 
            edad=form.cleaned_data["edad"],        
            direccion=form.cleaned_data["direccion"],
            telefono=form.cleaned_data["telefono"],
            terms_cond=form.cleaned_data["terms_cond"], 
        )
        messages.success(request, "Cuenta de cliente creada.")
        login(request, user)  # opcional: auto-login
        return redirect("cliente_panel")
    return render(request, "accounts/registro_form.html", {"form": form, "titulo": "Registro Cliente"})

def registro_farmacia(request):
    form = RegistroFarmaciaForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        user = form.save() ##
        obras_sociales_seleccionadas=form.cleaned_data.pop("obras_sociales")
        farmacia = Farmacia.objects.create(
            user=user,
            nombre=form.cleaned_data["nombre"],
            direccion=form.cleaned_data["direccion"],
            latitud=form.cleaned_data.get("latitud"),
            longitud=form.cleaned_data.get("longitud"),
            cuit=form.cleaned_data["cuit"],
            cbu=form.cleaned_data["cbu"],
            documentacion=form.cleaned_data["documentacion"],
            acepta_tyc=form.cleaned_data["acepta_tyc"],
            valido=True,     
        )
        farmacia.obras_sociales.set(obras_sociales_seleccionadas)
        login(request, user)
        messages.success(request, "Cuenta de farmacia creada.")
        #messages.success(request, "Cuenta de farmacia creada. Quedará pendiente de validación por un administrador.")
        return redirect("login")       
    return render(request, "accounts/registro_form.html", {"form": form, "titulo": "Registro Farmacia"})

def registro_repartidor(request):
    form = RegistroRepartidorForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        repartidor = Repartidor.objects.create(
            user=user,
            cuit=form.cleaned_data.get("cuit"),
            cbu=form.cleaned_data.get("cbu"),
            vehiculo=form.cleaned_data.get("vehiculo"),
            patente=form.cleaned_data.get("patente"),
            antecedentes=form.cleaned_data.get("antecedentes"),
            valido = True, # Para facilitar pruebas, se setea como válido directamente. Cambiar a False para requerir validación manual.
        )
        login(request, user)
        messages.success(request, "Cuenta de repartidor creada.")
        #messages.success(request, "Cuenta de repartidor creada. Quedará pendiente de validación por un administrador.")
        return redirect("login")
    return render(request, "accounts/registro_form.html", {"form": form, "titulo": "Registro Repartidor"})



@login_required(login_url='login')
def panel_principal(request):
    if es_cliente(request.user):
        return redirect("cliente_panel")
    elif es_farmacia(request.user):
        return redirect("farmacia_panel")
    elif es_repartidor(request.user):
        return redirect("repartidor_panel")
    else:
        return HttpResponseForbidden("Perfil no reconocido.")

