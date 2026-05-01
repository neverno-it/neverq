from django.apps import AppConfig


class ApiConfig(AppConfig):
    name = 'apps.api'
    verbose_name = 'Mobile API'

    def ready(self):
        import apps.api.signals  # noqa: F401
