from django.contrib import admin

from apps.models import Topic, TelegramChannel, TelegramDelivery, Classification, Article, Summary, ArticleImage


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    pass


@admin.register(TelegramChannel)
class TelegramChannelAdmin(admin.ModelAdmin):
    pass


@admin.register(TelegramDelivery)
class TelegramDeliveryAdmin(admin.ModelAdmin):
    pass


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    pass


@admin.register(Classification)
class ClassificationAdmin(admin.ModelAdmin):
    pass

@admin.register(ArticleImage)
class ArticleImageAdmin(admin.ModelAdmin):
    pass


@admin.register(Summary)
class SummaryAdmin(admin.ModelAdmin):
    pass
