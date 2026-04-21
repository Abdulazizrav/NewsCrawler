# Generated migration for adding summarize failure tracking fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('apps', '0006_scheduledsend'),
    ]

    operations = [
        migrations.AddField(
            model_name='article',
            name='last_summarize_attempt',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='article',
            name='summarize_failed_count',
            field=models.IntegerField(default=0),
        ),
    ]
