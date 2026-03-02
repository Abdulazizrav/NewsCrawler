from django.db import models
from django.db.models import CASCADE

from apps.models.summary import Summary
from apps.models.telegram_channel import TelegramChannel


class TelegramDelivery(models.Model):
    summary = models.ForeignKey(Summary,
                                on_delete=CASCADE,
                                related_name="telegram_deliveries")
    telegram_channel = models.ForeignKey(TelegramChannel,
                                         on_delete=CASCADE,
                                         related_name="telegram_deliveries")

    message_id = models.PositiveIntegerField(default=0)
    sent_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=255)
    cost_charged = models.DecimalField(decimal_places=2, max_digits=12)

    def __str__(self):
        return f"Delivery {self.telegram_channel.name}"

    class Meta:
        db_table = "TelegramDelivery"

