import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.files.base import ContentFile  # <--- IMPORTANTE: Para crear archivos en memoria
from apps.accounts.models import Cliente, Farmacia, Repartidor, ObraSocial

User = get_user_model()

class Command(BaseCommand):
    help = 'Puebla la DB con usuarios de prueba y genera un archivo de credenciales.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING('--- INICIANDO CARGA DE DATOS DEMO ---'))

        # 1. Definimos los usuarios de prueba
        usuarios_demo = [
            {
                "rol": "ADMIN",
                "email": "admin@farmago.com",
                "password": "admin123",
                "username": "admin_demo"
            },
            {
                "rol": "CLIENTE",
                "email": "cliente@farmago.com",
                "password": "cliente123",
                "username": "cliente_demo",
                "datos_perfil": {
                    "nombre": "Juan", "apellido": "Pérez", "documento": 11111111,
                    "edad": 30, "direccion": "Calle Falsa 123", "telefono": 1122334455,
                    "terms_cond": True
                }
            },
            {
                "rol": "FARMACIA",
                "email": "farmacia@farmago.com",
                "password": "farmacia123",
                "username": "farmacia_demo",
                "datos_perfil": {
                    "nombre": "Farmacia Central", "direccion": "Av. Siempreviva 742",
                    "cuit": "30-11223344-5", "cbu": "0000000000000000000001",
                    "acepta_tyc": True, "valido": True, "latitud": -34.9214, "longitud": -57.9545
                }
            },
            {
                "rol": "REPARTIDOR",
                "email": "repartidor@farmago.com",
                "password": "repartidor123",
                "username": "repartidor_demo",
                "datos_perfil": {
                    "cuit": "20-99887766-5", "cbu": "0000000000000000000002",
                    "vehiculo": "moto", "patente": "ABC-123",
                    "disponible": True, "valido": True
                }
            }
        ]

        credenciales_txt = "=== CREDENCIALES DE ACCESO (DEMO) ===\n\n"

        # 2. Creamos Obra Social básica
        os_demo, _ = ObraSocial.objects.get_or_create(nombre="OSDE")

        # 3. Iteramos y creamos
        for data in usuarios_demo:
            # Crear o recuperar Usuario base
            user, created = User.objects.get_or_create(
                email=data["email"],
                defaults={
                    "username": data["username"],
                    "is_staff": (data["rol"] == "ADMIN"),
                    "is_superuser": (data["rol"] == "ADMIN")
                }
            )
            
            user.set_password(data["password"])
            user.save()

            if created:
                self.stdout.write(self.style.SUCCESS(f'✓ Usuario creado: {data["email"]}'))
            else:
                self.stdout.write(f'- Usuario ya existía: {data["email"]}')

            # --- LÓGICA DE PERFILES CON ARCHIVOS FALSOS ---
            if data["rol"] == "CLIENTE":
                Cliente.objects.get_or_create(user=user, defaults=data["datos_perfil"])
            
            elif data["rol"] == "FARMACIA":
                # Si el perfil ya existe, no hacemos nada. Si no, lo creamos con archivo falso.
                if not Farmacia.objects.filter(user=user).exists():
                    # Creamos archivo falso en memoria
                    archivo_dummy = ContentFile(b"Documentacion de prueba", name="doc_farmacia.pdf")
                    data["datos_perfil"]["documentacion"] = archivo_dummy
                    
                    farma = Farmacia.objects.create(user=user, **data["datos_perfil"])
                    farma.obras_sociales.add(os_demo)
            
            elif data["rol"] == "REPARTIDOR":
                # Igual para el repartidor, necesita antecedentes sí o sí
                if not Repartidor.objects.filter(user=user).exists():
                    # Creamos archivo falso en memoria
                    archivo_dummy = ContentFile(b"Antecedentes limpios", name="antecedentes.pdf")
                    data["datos_perfil"]["antecedentes"] = archivo_dummy
                    
                    Repartidor.objects.create(user=user, **data["datos_perfil"])

            # Agregar al texto final
            credenciales_txt += f"ROL: {data['rol']}\n"
            credenciales_txt += f"Email: {data['email']}\n"
            credenciales_txt += f"Clave: {data['password']}\n"
            credenciales_txt += "-" * 30 + "\n"

        # 4. Escribir el archivo TXT
        archivo_path = os.path.join(settings.BASE_DIR, 'credenciales_prueba.txt')
        with open(archivo_path, 'w', encoding='utf-8') as f:
            f.write(credenciales_txt)

        self.stdout.write(self.style.SUCCESS(f'\n✓ Archivo generado exitosamente en: {archivo_path}'))