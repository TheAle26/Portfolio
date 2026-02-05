from django.db import models
from django.contrib.auth.models import User

class Empresa(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre

class Dispositivo(models.Model):
    nombre = models.CharField(max_length=100, help_text="Ej: Hyundai Santa Fe AA 111 AA")
    imei = models.CharField(max_length=20, unique=True)
    
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='dispositivos')
    
    usuarios_permitidos = models.ManyToManyField(User, related_name='dispositivos_asignados', blank=True)

    def __str__(self):
        return f"{self.nombre} ({self.imei})"

# RELACIÓN 3: Extensión del Usuario para asignarle una Empresa
# Como usamos el User por defecto de Django, creamos un "Perfil" o "Empleado"
class Empleado(models.Model):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE)
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='empleados')
    puede_asignar = models.BooleanField(default=False)
    # Opcional: Cargo o Área por si querés filtrar más adelante
    area = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.usuario.username} - {self.empresa.nombre}"