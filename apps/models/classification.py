from django.db.models import Model, ForeignKey, CASCADE

from apps.models.topic import Topic


class Classification(Model):
    article = ForeignKey("Article", on_delete=CASCADE, related_name="article_classifications", null=True,
                         blank=True)
    topic = ForeignKey(Topic, on_delete=CASCADE, related_name="topic_classifications", null=True, blank=True)


    def __str__(self):
        article_title = self.article.title.title() if self.article else "No Article"
        topic_name = self.topic.name if self.topic else "No Topic"
        return f"ARTICLE: {article_title}, TOPIC: {topic_name}"

    class Meta:
        db_table = "Classification"
        unique_together = ("article", "topic")
