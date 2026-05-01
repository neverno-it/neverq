from django.apps import AppConfig


class POSConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.pos'
    label = 'pos'
    verbose_name = 'POS'
