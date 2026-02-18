from django import forms
from .models import Pedido, Medicamento, StockMedicamento
from django.core.validators import MinValueValidator
import decimal

class PedidoForm(forms.ModelForm):
    class Meta:
        model = Pedido
        fields = ["detalles"]  # widgets opcionales, no necesarios

class AddStockMedicamentoForm(forms.Form):
    medicamento = forms.ModelChoiceField(
        queryset=Medicamento.objects.order_by('nombre_comercial'),
        label="Medicamento",
        empty_label="Seleccione un medicamento..."
    )
    precio = forms.DecimalField(
        
        decimal_places=2,
        label="Precio de Venta ($)",
        validators=[MinValueValidator(decimal.Decimal('0.01'))], # Precio debe ser positivo
        widget=forms.NumberInput(attrs={'step': '0.01'})
    )
    stock_actual = forms.IntegerField(
        label="Stock Inicial",
        validators=[MinValueValidator(0)], # Stock no puede ser negativo
        min_value=0 # Atributo HTML5 para el input
    )
    
    def __init__(self, farmacia, *args, **kwargs):
        """ Sobrescribimos para filtrar medicamentos que la farmacia YA tiene en stock """
        super().__init__(*args, **kwargs)
        # Excluir medicamentos que ya están en el stock de ESTA farmacia
        medicamentos_en_stock_ids = StockMedicamento.objects.filter(farmacia=farmacia).values_list('medicamento_id', flat=True)
        self.fields['medicamento'].queryset = Medicamento.objects.exclude(id__in=medicamentos_en_stock_ids).order_by('nombre_comercial')
        if not self.fields['medicamento'].queryset.exists():
             self.fields['medicamento'].empty_label = "Ya tienes todos los medicamentos registrados en tu stock."
             self.fields['medicamento'].disabled = True
        
class EditStockMedicamentoForm(forms.ModelForm):
    """Formulario para editar precio y stock de un medicamento existente en el inventario."""
    precio = forms.DecimalField(
        
        decimal_places=2,
        label="Nuevo Precio ($)",
        validators=[MinValueValidator(decimal.Decimal('0.01'))],
        widget=forms.NumberInput(attrs={'step': '0.01'})
    )
    stock_actual = forms.IntegerField(
        label="Nuevo Stock",
        validators=[MinValueValidator(0)],
        min_value=0
    )

    class Meta:
        model = StockMedicamento
        fields = ['precio', 'stock_actual']

class FarmaciaAceptarPedidoForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.pedido = kwargs.pop("pedido")
        super().__init__(*args, **kwargs)

        # Crear un campo booleano para cada item que requiera receta
        for item in self.pedido.items.select_related("medicamento"):
            if item.medicamento.requiere_receta:
                field_name = f"confirmar_receta_{item.id}"
                self.fields[field_name] = forms.BooleanField(
                    required=False,
                    label=f"Confirmo la receta de {item.medicamento.nombre_comercial}",
                )

    def clean(self):
        cleaned = super().clean()
        errores = []

        # Verificar que TODAS las recetas requeridas estén marcadas
        for item in self.pedido.items.select_related("medicamento"):
            if item.medicamento.requiere_receta:
                field_name = f"confirmar_receta_{item.id}"
                if not cleaned.get(field_name):
                    errores.append(
                        f"Debes confirmar la receta de {item.medicamento.nombre_comercial}."
                    )

        if errores:
            raise forms.ValidationError(errores)

        return cleaned
