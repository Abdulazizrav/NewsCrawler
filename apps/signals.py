from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from apps.permissions import is_superadmin


@receiver(user_logged_in)
def on_user_login(sender, request, user, **kwargs):
    # Only start pipeline for channel admins, not superadmin
    if is_superadmin(user):
        return

    from apps.scheduler_manager import start_user_pipeline
    start_user_pipeline(user.id)