from django import forms 
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import *
from django.contrib.auth import get_user_model

from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Jugador # Asumiendo que Jugador está en el mismo apps.py



class UserRegisterForm(UserCreationForm):

    username = forms.CharField(label="Nombre de usuario")
    first_name = forms.CharField(label="Nombre")
    last_name = forms.CharField(label="Apellido")
    email = forms.EmailField(label='Email')
    password1 = forms.CharField(label="Contraseña", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Repetir contraseña", widget=forms.PasswordInput)


    fecha_nacimiento = forms.DateField(
        label="Fecha de nacimiento",
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    foto_perfil = forms.ImageField(
        label="Foto de perfil (opcional)",
        required=False, 
        widget=forms.FileInput
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ('first_name', 'last_name', 'email')

    def __str__(self):
        return self.usuario.username   
    
    class Meta:
        model = User
        fields = [
            'username',
            'first_name',
            'last_name',
            'email',
            'password1',
            'password2',
            'fecha_nacimiento'
        ]
        help_texts = {k: "" for k in fields}

User = get_user_model()

class UserEditForm(forms.ModelForm):
    # Campos extra
    password1 = forms.CharField(label='Nueva Contraseña', widget=forms.PasswordInput, required=False)
    password2 = forms.CharField(label='Repetir Nueva Contraseña', widget=forms.PasswordInput, required=False)
    password1 = forms.CharField(
        label='Nueva Contraseña',
        required=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'})
    )
    password2 = forms.CharField(
        label='Repetir Nueva Contraseña',
        required=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'})
    )
    fecha_nacimiento = forms.DateField(
        label="Fecha de nacimiento",
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    foto_perfil = forms.ImageField(
    label="Foto de perfil",
    required=False,
    widget=forms.FileInput  # Esto evita el checkbox "Limpiar"
)
    


    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        help_texts = {k: "" for k in fields}

    def __init__(self, *args, **kwargs):
        profile_instance = kwargs.pop('profile_instance', None)
        super().__init__(*args, **kwargs)
        if profile_instance:
            self.fields['fecha_nacimiento'].initial = profile_instance.fecha_nacimiento
            

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("password1")
        p2 = cleaned_data.get("password2")

        # Solo validamos si ambos campos están completos
        if p1 and p2:
            if p1 != p2:
                raise forms.ValidationError("Las contraseñas no coinciden.")
        # Si vino solo uno (o ninguno), lo ignoramos y permitimos el guardado
        return cleaned_data


    def save(self, user_instance, profile_instance, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('password1')
        if password:
            user.set_password(password)
        if commit:
            user.save()

        foto_nueva = self.cleaned_data.get('foto_perfil')
        if foto_nueva:
            # borrar la anterior si existe
            if profile_instance.foto_perfil and profile_instance.foto_perfil.name != 'default.jpg':
                profile_instance.foto_perfil.delete(save=False)
            profile_instance.foto_perfil = foto_nueva

        profile_instance.fecha_nacimiento = self.cleaned_data.get('fecha_nacimiento')
        profile_instance.save()
        return user



class JugadorForm(forms.ModelForm): # Esta clase se usará para crear y modificar
    class Meta:
        model = Jugador
        fields = ['apodo', 'posicion', 'numero'] # Ahora solo estos campos. Quité 'activo' por simplicidad si no lo necesitan al crear.
        widgets = {
            'apodo': forms.TextInput(attrs={'class': 'form-control'}),
            'posicion': forms.Select(attrs={'class': 'form-select'}),
            'numero': forms.NumberInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.liga = kwargs.pop('liga', None) # Se sigue esperando 'liga' al instanciar
        super().__init__(*args, **kwargs)

    def clean_apodo(self):
        apodo = self.cleaned_data['apodo']
        # Al crear un jugador, instance.id será None. Al modificar, será el ID del jugador.
        # Esto asegura que el apodo sea único en la liga, excluyendo al jugador actual si estamos modificando.
        query = Jugador.objects.filter(liga=self.liga, apodo__iexact=apodo)
        if self.instance and self.instance.pk: # Si estamos modificando un jugador existente
            query = query.exclude(pk=self.instance.pk)
        if query.exists():
            raise forms.ValidationError("Este apodo ya está en uso en esta liga. Por favor, elige otro.")
        return apodo

class CrearYAsociarJugadorForm(forms.Form):
    username_usuario = forms.CharField(
        label="Nombre de Usuario existente",
        help_text="Introduce el nombre de usuario de la cuenta a asociar. El usuario debe existir y no tener un jugador ya asociado en esta liga.",
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_username_usuario'})
    )
    apodo = forms.CharField(
        max_length=50,
        label="Apodo del Jugador",
        help_text="El apodo debe ser único en esta liga.",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    posicion = forms.ChoiceField(
        choices=Jugador.OPCIONES, 
        label="Posición",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    numero = forms.IntegerField(
        required=False,
        label="Número de Camiseta",
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )

    def __init__(self, *args, **kwargs):
        self.liga = kwargs.pop('liga', None)
        super().__init__(*args, **kwargs)

    def clean_username_usuario(self):
        username = self.cleaned_data['username_usuario']
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise forms.ValidationError("No se encontró ningún usuario con este nombre de usuario.")
        
        # Si el usuario ya tiene un jugador en esta liga, lanzar error
        if self.liga and Jugador.objects.filter(liga=self.liga, usuario=user).exists():
            raise forms.ValidationError(f"Este usuario ('{username}') ya tiene un perfil de jugador asociado en esta liga.")
            
        return user # <--- ¡CAMBIO AQUÍ! Devuelve el objeto User, no el string.

    def clean_apodo(self):
        apodo = self.cleaned_data['apodo']
        if self.liga and Jugador.objects.filter(liga=self.liga, apodo__iexact=apodo).exists():
            raise forms.ValidationError("Este apodo ya está en uso en esta liga. Por favor, elige otro.")
        return apodo
    

class AsociarUsuarioForm(forms.Form):
    username_usuario = forms.CharField(
        label="Nombre de Usuario para Asociar",
        help_text="Introduce el nombre de usuario de la cuenta a asociar. El usuario debe existir y no tener un jugador ya asociado en esta liga.",
        widget=forms.TextInput(attrs={'class': 'form-control'}) # Ya no necesitamos forzar el ID aquí, Django lo hará
    )

    def __init__(self, *args, **kwargs):
        self.liga = kwargs.pop('liga', None)
        self.jugador_a_asociar = kwargs.pop('jugador_a_asociar', None)
        super().__init__(*args, **kwargs)


    def clean_username_usuario(self):
        username = self.cleaned_data['username_usuario']
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise forms.ValidationError("No se encontró ningún usuario con este nombre de usuario.")
        
        if self.jugador_a_asociar and self.jugador_a_asociar.usuario == user:
            return user

        if self.liga and Jugador.objects.filter(liga=self.liga, usuario=user).exists():
            raise forms.ValidationError(f"El usuario '{username}' ya tiene un perfil de jugador asociado en esta liga.")
            
        return user
    
    

class LigaForm(forms.ModelForm):
    class Meta:
        model = Liga
        fields = ['nombre_liga','descripcion']
        labels = {
            'nombre_liga': 'Nombre de la liga',
            'descripcion': 'Descripccion de la liga'
        }
        widgets = {
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Descripción'}),
        }
        help_texts = {
            'nombre_liga': 'Ingrese un nombre único para la liga.'
        }
        error_messages = {
            'nombre_liga': {
                'unique': "Ya existe una liga con este nombre. Por favor, elige otro nombre.",
            },
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields.pop('nombre_liga', None)

        

# class MiJugadorForm(JugadorForm):
#     class Meta(JugadorForm.Meta):
#         # Por ejemplo, podrías agregar o modificar campos, si fuera necesario.
#         pass


#     def __init__(self, *args, **kwargs):
#         # Se espera recibir el usuario logueado para filtrar las ligas
#         user = kwargs.pop('user', None)
#         super().__init__(*args, **kwargs)
#         if user:
#             # Obtener los IDs de las ligas en las que el usuario ya tiene un jugador.
#             user_league_ids = Jugador.objects.filter(usuario=user).values_list('liga', flat=True)
#            # Filtrar el queryset del campo liga para excluir esas ligas.
#             self.fields['liga'].queryset = Liga.objects.exclude(id__in=user_league_ids)


class PartidoForm(forms.ModelForm):
    # Ya no definimos 'jugadores' aquí directamente, se manejará en __init__

    class Meta:
        model = Partido
        fields = ['fecha_partido', 'cancha'] # Solo estos campos son parte del modelo Partido directamente
        labels = {
            'fecha_partido': 'Fecha del partido',
            'cancha': 'Cancha',
        }
        widgets = {
            'fecha_partido': forms.DateInput(attrs={'type': 'date'}),
        }
    
    def __init__(self, *args, **kwargs):
        league = kwargs.pop('league', None)
        # Una forma de saber si estamos modificando es si hay una 'instance'
        is_modifying = kwargs.get('instance') is not None 

        super().__init__(*args, **kwargs)

        if not is_modifying: # Solo agrega el campo jugadores si es un formulario de creación
            self.fields['jugadores'] = forms.ModelMultipleChoiceField(
                queryset=None,  # Se define más abajo
                widget=forms.CheckboxSelectMultiple,
                required=False,
                label="Jugadores que participaron"
            )
            if league:
                self.fields['jugadores'].queryset = league.jugadores.all()
        # Si es un formulario de modificación, no agregamos el campo 'jugadores'
        # para que no sea editable.
        if is_modifying and self.instance and self.instance.fecha_partido:

                    self.initial['fecha_partido'] = self.instance.fecha_partido.isoformat()


class SimularPartidoForm(forms.Form):
    # Campo adicional para seleccionar los jugadores de la liga que participaron.
    jugadores = forms.ModelMultipleChoiceField(
        queryset=None,  # Lo definiremos en __init__
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Jugadores que participaron"
    )
    def __init__(self, *args, **kwargs):
        # Esperamos recibir la instancia de la liga (league) para filtrar los jugadores.
        league = kwargs.pop('league', None)
        super().__init__(*args, **kwargs)
        if league:
            # El queryset del campo 'jugadores' se limita a los jugadores de esa liga.
            self.fields['jugadores'].queryset = league.jugadores.all()

# class MensajeForm(forms.ModelForm):
#     class Meta:
#         model = Mensaje
#         fields = ['remitente', 'contenido']
#         widgets = {
#             'remitente': forms.Select(attrs={'class': 'form-control'}),
#             'contenido': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
#         }
