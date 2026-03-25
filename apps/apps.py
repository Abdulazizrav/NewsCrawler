from django.apps import AppConfig
import os


class AppsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps'

    def ready(self):
        import apps.signals  # noqa

        # Delay DB query until after app is fully ready
        from django.db import connection
        try:
            connection.ensure_connection()
        except Exception:
            return  # DB not available, skip startup pipelines

        if os.environ.get('DYNO') or os.environ.get('RUN_MAIN'):
            from django.db import close_old_connections
            close_old_connections()
            self._start_pipelines()

    def _start_pipelines(self):
        try:
            from django.contrib.auth import get_user_model
            from apps.scheduler_manager import start_user_pipeline
            from apps.permissions import is_superadmin

            User = get_user_model()
            users = User.objects.filter(is_active=True)
            for user in users:
                if not is_superadmin(user):
                    start_user_pipeline(user.id)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Could not start pipelines on startup: {e}")