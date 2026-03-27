from django.apps import AppConfig
import os


class AppsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps'

    def ready(self):
        import apps.signals  # noqa

        # Skip during migrations and management commands
        if any(cmd in os.sys.argv for cmd in ['migrate', 'makemigrations', 'collectstatic', 'shell']):
            return

        from django.db import close_old_connections
        try:
            close_old_connections()
            from apps.scheduler_manager import start_scheduled_send_checker
            start_scheduled_send_checker()
            self._start_pipelines()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Startup error: {e}")

    def _start_pipelines(self):
        try:
            from django.contrib.auth import get_user_model
            from apps.scheduler_manager import start_user_pipeline
            from apps.permissions import is_superadmin
            from django.db import close_old_connections

            close_old_connections()
            User = get_user_model()
            users = User.objects.filter(is_active=True)
            for user in users:
                if not is_superadmin(user):
                    start_user_pipeline(user.id)
                    import logging
                    logging.getLogger(__name__).info(f"✅ Pipeline started for user {user.id}")
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Could not start pipelines: {e}")