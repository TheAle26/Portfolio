import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.files.base import ContentFile
from apps.accounts.models import Cliente, Farmacia, Repartidor, ObraSocial
from apps.orders.models import Medicamento, StockMedicamento

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
        os_list = []
        os_list.append(ObraSocial.objects.get_or_create(nombre="OSDE")[0])
        os_list.append(ObraSocial.objects.get_or_create(nombre="IOMA")[0])
        os_list.append(ObraSocial.objects.get_or_create(nombre="Swiss Medical")[0])
        ObraSocial.objects.get_or_create(nombre="Galeno")
        
        # 3. Iteramos y creamos USUARIOS Y PERFILES PRIMERO
        self.stdout.write(self.style.WARNING('\n--- CARGANDO USUARIOS ---'))
        for data in usuarios_demo:
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

            # LÓGICA DE PERFILES
            if data["rol"] == "CLIENTE":
                Cliente.objects.get_or_create(user=user, defaults=data["datos_perfil"])
            
            elif data["rol"] == "FARMACIA":
                if not Farmacia.objects.filter(user=user).exists():
                    archivo_dummy = ContentFile(b"Documentacion de prueba", name="doc_farmacia.pdf")
                    data["datos_perfil"]["documentacion"] = archivo_dummy
                    
                    farma = Farmacia.objects.create(user=user, **data["datos_perfil"])
                    for os_obj in os_list:
                        farma.obras_sociales.add(os_obj)
            
            elif data["rol"] == "REPARTIDOR":
                if not Repartidor.objects.filter(user=user).exists():
                    archivo_dummy = ContentFile(b"Antecedentes limpios", name="antecedentes.pdf")
                    data["datos_perfil"]["antecedentes"] = archivo_dummy
                    
                    Repartidor.objects.create(user=user, **data["datos_perfil"])

            credenciales_txt += f"ROL: {data['rol']}\n"
            credenciales_txt += f"Email: {data['email']}\n"
            credenciales_txt += f"Clave: {data['password']}\n"
            credenciales_txt += "-" * 30 + "\n"

        # 4. AHORA SÍ: Creamos medicamentos y stock para la farmacia demo
        self.stdout.write(self.style.WARNING('\n--- CARGANDO MEDICAMENTOS E INVENTARIO ---'))
        
        medicamentos_demo = [
            {"nombre_comercial": "Ibuprofeno 600", "principio_activo": "Ibuprofeno", "concentracion": "600mg", "categoria": "Analgésico", "requiere_receta": False, "codigo_barra": "7791234567801", "precio_simulado": 1500.00, "stock_simulado": 50},
            {"nombre_comercial": "Amoxidal", "principio_activo": "Amoxicilina", "concentracion": "500mg", "categoria": "Antibiótico", "requiere_receta": True, "codigo_barra": "7791234567802", "precio_simulado": 3200.00, "stock_simulado": 20},
            {"nombre_comercial": "Tafirol", "principio_activo": "Paracetamol", "concentracion": "1g", "categoria": "Analgésico", "requiere_receta": False, "codigo_barra": "7791234567803", "precio_simulado": 1100.00, "stock_simulado": 100},
            {"nombre_comercial": "Alplax", "principio_activo": "Alprazolam", "concentracion": "1mg", "categoria": "Ansiolítico", "requiere_receta": True, "codigo_barra": "7791234567804", "precio_simulado": 4500.00, "stock_simulado": 15},
            {"nombre_comercial": "Aerotina", "principio_activo": "Loratadina", "concentracion": "10mg", "categoria": "Antihistamínico", "requiere_receta": False, "codigo_barra": "7791234567805", "precio_simulado": 1800.00, "stock_simulado": 40},
        ]

        # Recuperamos la farmacia que YA SE CREÓ arriba
        farmacia_central = Farmacia.objects.get(user__email="farmacia@farmago.com")

        for med_data in medicamentos_demo:
            precio = med_data.pop("precio_simulado")
            stock = med_data.pop("stock_simulado")

            medicamento, med_created = Medicamento.objects.get_or_create(
                nombre_comercial=med_data["nombre_comercial"],
                concentracion=med_data["concentracion"],
                defaults=med_data
            )

            # CORRECCIÓN AQUÍ: Usamos una variable en minúscula 'stock_item'
            stock_item, stock_created = StockMedicamento.objects.update_or_create(
                farmacia=farmacia_central,
                medicamento=medicamento,
                defaults={
                    "precio": precio,
                    "stock_actual": stock
                }
            )

            if med_created:
                self.stdout.write(f'  + Medicamento global creado: {medicamento.nombre_comercial}')
            if stock_created:
                self.stdout.write(self.style.SUCCESS(f'    ✓ Agregado al stock de {farmacia_central.nombre} (Cant: {stock})'))

        # 5. Escribir el archivo TXT
        archivo_path = os.path.join(settings.BASE_DIR, 'credenciales_prueba.txt')
        with open(archivo_path, 'w', encoding='utf-8') as f:
            f.write(credenciales_txt)

        self.stdout.write(self.style.SUCCESS(f'\n✓ Archivo generado exitosamente en: {archivo_path}'))