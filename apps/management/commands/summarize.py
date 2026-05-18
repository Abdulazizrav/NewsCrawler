import os
import json
import re

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from dotenv import load_dotenv
from django.db import close_old_connections
from django.utils import timezone

from apps.models import Summary, Article
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, Semaphore
import datetime

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
stats_lock = Lock()
openai_semaphore = Semaphore(5)
processing_lock = Lock()
processing_ids = set()  # track articles currently being processed by any thread

MAX_SUMMARIZE_FAILURES = 3


def extract_text(response):
    try:
        return response.output[0].content[0].text.strip()
    except Exception:
        return ""


def clean_json_response(text: str) -> str:
    """Extracts JSON from a string that might contain markdown or extra text."""
    # Try to find content between the first { and last }
    match = re.search(r'(\{.*\})', text, re.DOTALL)
    if match:
        return match.group(1)
    return text.strip()


def summarize_and_translate_with_openai(text: str, title: str, tone: str = "Neutral") -> str:
    """
    Returns a single, fully translated block of text in Uzbek with a specific tone.
    The first line is the translated title, followed by the summary.
    """
    tone_instructions = {
        "Formal": "Use a highly Formal, professional, and authoritative tone. Avoid slang or casual language.",
        "Neutral": "Use a Neutral, balanced, and objective tone. Stick to facts.",
        "Informal": "Use an Informal, friendly, and conversational tone. You can be more engaging and direct."
    }
    tone_desc = tone_instructions.get(tone, tone_instructions["Neutral"])

    with openai_semaphore:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional news translator and summarizer. "
                        f"CRITICAL: {tone_desc}\n\n"
                        "Translate the article title and provide only the most critical factual details as bullet points.\n\n"
                        "FORMATTING RULES:\n"
                        "1. The FIRST line must be the translated title in Uzbek (no emojis, just text).\n"
                        "2. Followed by a blank line.\n"
                        "3. Then provide 2-4 factual bullet points starting with 🔹.\n"
                        "4. CRITICAL: NEVER repeat the information already stated in the title. The bullet points MUST contain ONLY new, unique, and additional facts that elaborate on the title. Skip the obvious.\n"
                        "5. CRITICAL: NO introductory sentence. Jump straight into the new facts.\n"
                        "6. Return ONLY the translated Uzbek text."
                    )
                },
                {
                    "role": "user",
                    "content": f"Title: {title}\n\nContent: {text}"
                }
            ],
            temperature=0.1,
            max_tokens=500
        )

    return response.choices[0].message.content.strip()


def process_article_for_channel(article, channel, stats):
    """Process single article for a specific channel with its specific tone"""
    # Claim this (article, channel) pair atomically
    task_id = f"{article.id}_{channel.id}"
    with processing_lock:
        if task_id in processing_ids:
            return
        processing_ids.add(task_id)

    try:
        # Check if summary already exists for this channel
        if Summary.objects.filter(article=article, telegram_channel=channel).exists():
            with stats_lock:
                stats["skipped"] += 1
            return

        if article.summarize_failed_count >= MAX_SUMMARIZE_FAILURES:
            with stats_lock:
                stats["skipped"] += 1
            return

        if not article.content or len(article.content) < 50:
            with stats_lock:
                stats["skipped"] += 1
            return

        print(f"--- [PROCESSING] Summarizing article {article.id} for channel '{channel.name}' (Tone: {channel.tone})...")
        full_content = summarize_and_translate_with_openai(
            article.content,
            article.title,
            channel.tone
        )

        # Split the first line as the title for the article itself (optional, might overwrite)
        lines = full_content.split('\n')
        translated_title = lines[0].strip()
        if len(translated_title) < 5:
            translated_title = article.title

        Summary.objects.create(
            article=article,
            telegram_channel=channel,
            summary_text=full_content
        )

        # Mark article as summarized globally (at least once)
        article.is_summary = True
        article.title = translated_title  # This updates the main article title to the latest translated one
        article.summarize_failed_count = 0 
        article.last_summarize_attempt = timezone.now()
        article.save()

        print(f"+++ [SUCCESS] Article {article.id} summarized for channel {channel.id}.")
        with stats_lock:
            stats["processed"] += 1

    except Exception as e:
        print(f"Error processing article {article.id} for channel {channel.id}: {e}")
        with stats_lock:
            stats["failed"] += 1
        article.summarize_failed_count += 1
        article.last_summarize_attempt = timezone.now()
        article.save()

    finally:
        with processing_lock:
            processing_ids.discard(task_id)


class Command(BaseCommand):
    help = "Summarize articles and translate titles for a specific user"

    def add_arguments(self, parser):
        parser.add_argument('--user_id', type=int, required=True)

    def handle(self, *args, **options):
        close_old_connections()
        user = User.objects.get(id=options["user_id"])
        print(f"=== [START] Summarization started for user: {user.username} (ID: {user.id})")

        start = datetime.datetime.now()

        # Reset stats per run (not global state)
        stats = {"processed": 0, "failed": 0, "skipped": 0}

        # Get active channels for this user
        from apps.models import TelegramChannel
        channels = TelegramChannel.objects.filter(owner=user, is_active=True).select_related('topic')

        tasks = []
        for channel in channels:
            # Get articles for this channel's topic that don't have a summary for THIS channel yet
            # and haven't failed too many times
            articles = Article.objects.filter(
                owner=user,
                article_classifications__topic=channel.topic
            ).exclude(
                summaries__telegram_channel=channel
            ).filter(
                summarize_failed_count__lt=MAX_SUMMARIZE_FAILURES
            ).distinct()

            for article in articles:
                tasks.append((article, channel))

        if not tasks:
            self.stdout.write("No articles to summarize.")
            return

        self.stdout.write(f"Found {len(tasks)} Article-Channel pairs to process...")

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(process_article_for_channel, t[0], t[1], stats) for t in tasks]
            for f in as_completed(futures):
                f.result()

        duration = datetime.datetime.now() - start

        self.stdout.write(
            self.style.SUCCESS(
                f"Done in {duration} | "
                f"Processed: {stats['processed']} | "
                f"Failed: {stats['failed']} | "
                f"Skipped: {stats['skipped']}"
            )
        )
