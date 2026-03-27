from django.apps import AppConfig
import os


class AppsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps'

    def ready(self):
        import apps.signals  # noqa

        if any(cmd in os.sys.argv for cmd in ['migrate', 'makemigrations', 'collectstatic', 'shell', 'check']):
            return

        # ✅ Never touch DB in ready() — do everything in a delayed background thread
        import threading
        import time

        def delayed_start():
            time.sleep(60)  # ✅ wait 60 seconds instead of 15
            try:
                from apps.scheduler_manager import start_scheduled_send_checker, start_all_pipelines
                start_scheduled_send_checker()
                start_all_pipelines()
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Startup error: {e}")

        threading.Thread(target=delayed_start, daemon=True, name="startup-delay").start()