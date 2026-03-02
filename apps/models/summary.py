from django.db.models import Model, ForeignKey, CASCADE, TextField, DateTimeField


class Summary(Model):
    article = ForeignKey("Article", on_delete=CASCADE, related_name="summaries", null=True, blank=True)
    summary_text = TextField(null=True, blank=True)
    created_date = DateTimeField(auto_now_add=True, blank=True, null=True)

    def __str__(self):
        return f"{self.article.title.title()}"

    class Meta:
        db_table = "Summary"


