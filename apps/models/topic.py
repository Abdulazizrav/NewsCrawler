from django.contrib.auth.models import User
from django.db import models
from django.db.models import CASCADE


class Topic(models.Model):
    owner = models.ForeignKey(User, on_delete=CASCADE, related_name="topics", null=True, blank=True)
    name = models.CharField(max_length=100)
    keywords = models.CharField(max_length=255)

    def __str__(self):
        return self.name

    class Meta:
        db_table = "Topic"


