from django.contrib.auth.models import User
from django.db import models
from django.db.models import CASCADE

from apps.models.topic import Topic


class TelegramChannel(models.Model):
    owner = models.ForeignKey(User, on_delete=CASCADE, related_name="telegram_channels", null=True, blank=True)
    name = models.CharField(max_length=100)
    channel_id = models.BigIntegerField(default=0)
    # topic = models.URLField()
    price_per_message = models.DecimalField(max_digits=12, decimal_places=2)
    balance = models.DecimalField(max_digits=12, decimal_places=2)
    is_active = models.BooleanField(default=False)
    last_payment_date = models.DateTimeField(null=True, blank=True)

    topic = models.ForeignKey(Topic, on_delete=CASCADE, related_name="telegram_channels")

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'TelegramChannel'


