from django import forms
from django.contrib.auth.forms import UserCreationForm
# Importar para manejar errores de validación
from django.core.exceptions import ValidationError 
# Importar para validadores de rango
from django.core.validators import MinValueValidator, MaxValueValidator
from .models import Cliente, Farmacia, ObraSocial, Repartidor
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError
import re
from django.contrib.auth import get_user_model
User = get_user_model()

def validate_file_size(value):
    max_mb = 5
    if value.size > max_mb * 1024 * 1024:
        raise ValidationError(f'El archivo no puede superar {max_mb} MB.')


class BaseRegistroForm(UserCreationForm):
    class Meta:
        model = User
        fields = ["email"]  #settings.AUTH_USER_MODELtiene email como USERNAME_FIELD


class RegistroClienteForm(BaseRegistroForm):
    nombre = forms.CharField(max_length=30)
    apellido = forms.CharField(max_length=30)
    documento = forms.IntegerField(validators=[MinValueValidator(0)])
    edad = forms.IntegerField(validators=[MinValueValidator(18), MaxValueValidator(120)])
    direccion = forms.CharField(max_length=255)
    telefono = forms.IntegerField()
    terms_cond = forms.BooleanField(label="Acepto los términos y condiciones")
    
    class Meta(BaseRegistroForm.Meta):
        fields = BaseRegistroForm.Meta.fields + ["password1","password2","nombre","apellido","documento","edad","direccion", "telefono","terms_cond"]
    def clean_nombre(self):
        nombre = self.cleaned_data.get('nombre')
        # Regex: ^[...]*$
        # ^ -> Comienzo de la cadena
        # [a-zA-Z\s] -> Permite letras (minúsculas y mayúsculas) y espacios (\s)
        # * -> Cero o más veces
        # $ -> Fin de la cadena
        if not re.match(r"^[a-zA-Z\s]*$", nombre):
            raise ValidationError("El nombre solo puede contener letras y espacios.")
        return nombre

    def clean_apellido(self):
        apellido = self.cleaned_data.get('apellido')
        if not re.match(r"^[a-zA-Z\s]*$", apellido):
            raise ValidationError("El apellido solo puede contener letras y espacios.")
        return apellido
    
    # Validación personalizada para el campo 'documento'
    def clean_documento(self):
        documento = self.cleaned_data.get('documento')
        
        # Verifica si ya existe un cliente con ese número de documento.
        # Esto asume que el modelo 'Cliente' ya existe y está importado.
        if Cliente.objects.filter(documento=documento).exists():
            raise ValidationError("Ya existe un cliente registrado con este número de documento.")
        
        return documento # Si es único, devuelve el valor.

class RegistroFarmaciaForm(BaseRegistroForm):
    nombre = forms.CharField(max_length=100, label="Nombre de la farmacia")

    direccion = forms.CharField(
        max_length=255, 
        label="Dirección de la Sucursal",
        widget=forms.TextInput(attrs={'id': 'id_direccion_autocomplete'})
    )

    cuit = forms.CharField(max_length=13, label="CUIT", help_text="Formato XX-XXXXXXXX-X",
                           widget=forms.TextInput(attrs={'maxlength': 13, 'placeholder': '20-12345678-3'}))
    cbu = forms.CharField(max_length=22, label="CBU de la farmacia",
                          widget=forms.TextInput(attrs={'maxlength': 22, 'placeholder': '22 dígitos numéricos'}))
    obras_sociales = forms.ModelMultipleChoiceField(queryset=ObraSocial.objects.all(), widget = forms.CheckboxSelectMultiple, required=False, label="Obras Sociales Aceptadas")
    documentacion = forms.FileField(label="Documentación de la farmacia", validators = [FileExtensionValidator(allowed_extensions=['pdf', 'jpg', 'png'])], help_text="Archivos permitidos: PDF, JPG, PNG.")
    acepta_tyc = forms.BooleanField(label="Acepto los términos y condiciones y la Política de Privacidad.", required=True, error_messages={'required': 'Debes aceptar los términos y condiciones para registrarte.'})

    latitud = forms.DecimalField(
        widget=forms.HiddenInput(), 
        required=False, 
        max_digits=9, 
        decimal_places=6
    )
    longitud = forms.DecimalField(
        widget=forms.HiddenInput(), 
        required=False, 
        max_digits=9, 
        decimal_places=6
    )

    def clean_cuit(self):
        cuit = self.cleaned_data.get('cuit')
        if not cuit:
            return cuit

        # Normalizar la entrada: aceptar dígitos sueltos y formatear con guiones si vienen 11 dígitos
        digits = re.sub(r'\D', '', cuit)
        if len(digits) == 11:
            cuit = f"{digits[:2]}-{digits[2:10]}-{digits[10]}"
            self.cleaned_data['cuit'] = cuit

        if not re.match(r'^\d{2}-\d{8}-\d{1}$', cuit):
            raise ValidationError("Formato de CUIT inválido. Use XX-XXXXXXXX-X.")
        if Farmacia.objects.filter(cuit=cuit).exists() :
            raise ValidationError("Ya existe una farmacia registrada con este CUIT.")
        return cuit

class RegistroRepartidorForm(BaseRegistroForm):
    cuit = forms.CharField(max_length=13, label="CUIT", help_text="Formato XX-XXXXXXXX-X",
                           widget=forms.TextInput(attrs={'maxlength': 13, 'placeholder': '20-12345678-3'}))
    cbu = forms.CharField(max_length=22, label="CBU", required=True,
                          widget=forms.TextInput(attrs={'maxlength': 22, 'placeholder': '22 dígitos numéricos'}))
    vehiculo = forms.ChoiceField(choices=Repartidor.VEHICULO_CHOICES)
    patente = forms.CharField(max_length=7, required=False)
    antecedentes = forms.FileField(label="Antecedentes penales",
        required=True,
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'pdf']), validate_file_size],
        help_text='Archivo (JPG/PNG/PDF), máximo 5 MB.'
    )
    acepta_tyc = forms.BooleanField( 
        label="Acepto los términos y condiciones",
        required=True,
        error_messages={'required': 'Debes aceptar los términos y condiciones para registrarte.'}
        
    )

    class Meta(BaseRegistroForm.Meta):
        fields = BaseRegistroForm.Meta.fields + [
            "password1",
            "password2",
            "cuit",
            "cbu",
            "vehiculo",
            "patente",
            "antecedentes",
            "acepta_tyc",
        ]

    def clean_cuit(self):
        cuit = self.cleaned_data.get('cuit')
        if not cuit:
            return cuit

        # Normalizar: aceptar que el usuario ingrese solo dígitos y formatear con guiones
        digits = re.sub(r'\D', '', cuit)
        if len(digits) == 11:
            cuit = f"{digits[:2]}-{digits[2:10]}-{digits[10]}"
            # actualizar cleaned_data para que el valor formateado se use luego
            self.cleaned_data['cuit'] = cuit

        if not re.match(r'^\d{2}-\d{8}-\d{1}$', cuit):
            raise ValidationError("Formato de CUIT inválido. Use XX-XXXXXXXX-X.")
        if Repartidor.objects.filter(cuit=cuit).exists():
            raise ValidationError("Ya existe un repartidor registrado con este CUIT.")
        return cuit

    def clean_cbu(self):
        cbu = self.cleaned_data.get('cbu')
        if not cbu:
            return cbu
        digits = re.sub(r'\D', '', cbu)
        # CBU argentino tiene 22 dígitos
        if len(digits) != 22:
            raise ValidationError('El CBU debe contener exactamente 22 dígitos numéricos.')
        # normalizar a solo dígitos
        self.cleaned_data['cbu'] = digits
        return digits

    def clean(self):
        cleaned = super().clean()
        vehiculo = cleaned.get('vehiculo')
        patente = cleaned.get('patente')
        if vehiculo in (Repartidor.VEHICULO_AUTO, Repartidor.VEHICULO_MOTO) and not patente:
            self.add_error('patente', 'La patente es requerida para auto o moto.')
        if vehiculo == Repartidor.VEHICULO_BICI:
            cleaned['patente'] = None
        return cleaned