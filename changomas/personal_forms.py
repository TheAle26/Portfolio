from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models.functions import Lower

from .models import Supermarket


class RegistrationForm(forms.Form):
    email = forms.EmailField(max_length=254)
    password1 = forms.CharField(widget=forms.PasswordInput, strip=False)
    password2 = forms.CharField(widget=forms.PasswordInput, strip=False)

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        user_model = get_user_model()
        if user_model.objects.annotate(email_lower=Lower('email')).filter(email_lower=email).exists():
            raise forms.ValidationError('No pudimos completar el registro. Revisá los datos o intentá ingresar.')
        return email

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get('password1')
        if password and cleaned.get('password2') and password != cleaned['password2']:
            self.add_error('password2', 'Las contraseñas no coinciden.')
        if password and cleaned.get('email'):
            candidate = get_user_model()(email=cleaned['email'])
            try:
                validate_password(password, candidate)
            except ValidationError as exc:
                self.add_error('password1', exc)
        return cleaned


class EmailLoginForm(AuthenticationForm):
    username = forms.EmailField(label='Email')

    def clean_username(self):
        return self.cleaned_data['username'].strip().lower()


class SubscriptionForm(forms.Form):
    product_id = forms.IntegerField(min_value=1)
    target_price = forms.DecimalField(min_value=0.01, max_digits=12, decimal_places=2, required=False)
    promo_alert = forms.BooleanField(required=False, initial=True)
    stores = forms.ModelMultipleChoiceField(
        queryset=Supermarket.objects.none(),
        to_field_name='slug',
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['stores'].queryset = Supermarket.objects.filter(is_active=True).order_by('name')

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('target_price') is None and not cleaned.get('promo_alert'):
            raise forms.ValidationError('Elegí un precio objetivo o alertas de promociones.')
        return cleaned
