from django.contrib.auth.models import User
from django.db import models
from django.db.models import CASCADE


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('superadmin', 'Super Admin'),
        ('channel_admin', 'Channel Admin'),
    ]

    user = models.OneToOneField(User, on_delete=CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='channel_admin')
    created_by = models.ForeignKey(
        User, on_delete=CASCADE,
        related_name='created_users',
        null=True, blank=True
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_superadmin(self):
        return self.role == 'superadmin'

    def is_channel_admin(self):
        return self.role == 'channel_admin'

    def __str__(self):
        return f"{self.user.username} ({self.role})"

    class Meta:
        db_table = "UserProfile"