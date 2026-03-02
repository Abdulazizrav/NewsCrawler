from io import BytesIO
from PIL import Image
from django.contrib.auth.models import User
from django.db.models import Model, CharField, TextField, BooleanField, BinaryField, ForeignKey, SET_NULL, CASCADE
from django.db import models



class Article(Model):
    owner = models.ForeignKey(User, on_delete=CASCADE, related_name="articles", null=True, blank=True)
    title = TextField(null=True, blank=True)
    content = TextField(null=True, blank=True)
    url = TextField(null=True, blank=True)
    source = CharField(max_length=255, null=True, blank=True)
    published_date = CharField(max_length=255, null=True, blank=True)
    is_summary = BooleanField(default=False)

    def __str__(self):
        return f"{self.title} {self.id}"

    class Meta:
        db_table = "Article"


class ArticleImage(Model):
    image = BinaryField()
    article = ForeignKey("apps.Article", blank=True, null=True, on_delete=CASCADE, related_name="images")

    def save(self, *args, **kwargs):
        if self.image:
            img = Image.open(BytesIO(self.image))
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
            img_io = BytesIO()
            img.save(img_io, format='JPEG', quality=75, optimize=True)
            self.image = img_io.getvalue()

        super().save(*args, **kwargs)
