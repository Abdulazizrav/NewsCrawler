from django.db import models
from django.utils import timezone

class FieldHint(models.Model):
    FIELD_CHOICES = [
        ('channel_name', 'Channel Name'),
        ('channel_id', 'Channel ID'),
        ('topic', 'Topic'),
        ('tone', 'Summary Tone'),
    ]

    field_name = models.CharField(
        max_length=50, 
        choices=FIELD_CHOICES, 
        unique=True,
        help_text="The form field this video provides a hint for."
    )
    video_data = models.BinaryField(
        blank=True, 
        null=True,
        help_text="Raw video file data."
    )
    content_type = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        help_text="MIME type of the video, e.g., video/mp4."
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Hint for {self.get_field_name_display()}"
