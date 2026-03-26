# apps/models/scheduled_send.py
from django.db import models
from django.contrib.auth.models import User
from apps.models.summary import Summary
from apps.models.telegram_channel import TelegramChannel


class ScheduledSend(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    summary_ids = models.TextField()        # comma-separated
    channel_ids = models.TextField()        # comma-separated
    scheduled_time = models.DateTimeField()
    is_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def get_summary_ids(self):
        return [int(i) for i in self.summary_ids.split(',') if i.strip()]

    def get_channel_ids(self):
        return [int(i) for i in self.channel_ids.split(',') if i.strip()]

    def __str__(self):
        return f"ScheduledSend(user={self.user_id}, time={self.scheduled_time}, sent={self.is_sent})"