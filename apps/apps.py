from django.apps import AppConfig
import os


class AppsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps'

    def ready(self):
        import apps.signals  # noqa

        # ✅ Only run in ONE worker process, not all gunicorn workers
        if not os.environ.get('DYNO') and not os.environ.get('RUN_MAIN'):
            return

        # ✅ Use a lock file to ensure only ONE worker starts the scheduler
        import tempfile
        lock_file = os.path.join(tempfile.gettempdir(), 'newscrawler_scheduler.lock')
        try:
            # Try to create lock file exclusively
            fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
        except FileExistsError:
            # Another worker already started the scheduler
            return

        from django.db import close_old_connections
        close_old_connections()

        from apps.scheduler_manager import start_scheduled_send_checker
        start_scheduled_send_checker()
        self._start_pipelines()

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
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Could not start pipelines on startup: {e}")
