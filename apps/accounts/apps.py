from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"   # <- IMPORTANTE
    label = "accounts"       # opcional, mantiene app_label corto
