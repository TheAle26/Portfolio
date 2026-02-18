from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager

class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("El Email debe ser configurado")
        
        email = self.normalize_email(email)
        
        # --- MAGIA AQUÍ: Auto-generar username si no lo envían ---
        if 'username' not in extra_fields:
            base_username = email.split('@')[0]
            username = base_username
            counter = 1
            # Bucle para asegurar que el username sea único
            while self.model.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1
            extra_fields['username'] = username
        # ---------------------------------------------------------

        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("activo", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser debe tener is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser debe tener is_superuser=True.")
            
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    # 1. BORRAMOS la línea que decía "username = None". ¡El username vuelve a la vida!
    
    email = models.EmailField(unique=True)
    activo = models.BooleanField(default=True)

    # 2. Mantenemos el email como el campo obligatorio para el Login
    USERNAME_FIELD = "email"
    
    # 3. Le decimos a Django que el username sigue existiendo
    REQUIRED_FIELDS = ['username']

    objects = CustomUserManager()

    def delete(self, *args, **kwargs):
        self.activo = False
        self.is_active = False
        self.save()

    def hard_delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
    
    def __str__(self):
        # 4. Ahora puedes devolver el username para que tus templates de AppFulbo funcionen perfecto
        return self.username