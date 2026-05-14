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


def summarize_and_translate_with_openai(text: str, title: str) -> str:
    """
    Returns a single, fully translated block of text in Uzbek.
    The first line is the translated title, followed by the summary.
    """
    with openai_semaphore:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional news translator and summarizer. "
                        "Translate the article title and summarize its content into a single, cohesive block of text in Uzbek.\n\n"
                        "FORMATTING RULES:\n"
                        "1. The FIRST line must be the translated title (no emojis, just the title).\n"
                        "2. Followed by a blank line.\n"
                        "3. Then the summary, starting with 📌.\n"
                        "4. Use 🔹 for bullet points.\n"
                        "5. Ensure ZERO repetition between the title and the summary details.\n"
                        "6. Return ONLY the translated Uzbek text."
                    )
                },
                {
                    "role": "user",
                    "content": f"Title: {title}\n\nContent: {text}"
                }
            ],
            temperature=0.2,
            max_tokens=600
        )

    return response.choices[0].message.content.strip()


def process_article(article, stats):
    """Process single article with failure tracking"""
    # Claim this article atomically — skip if another thread already took it
    with processing_lock:
        if article.id in processing_ids:
            with stats_lock:
                stats["skipped"] += 1
            return
        processing_ids.add(article.id)

    try:
        # Double-check in DB after claiming (handles re-runs)
        if article.is_summary or Summary.objects.filter(article=article).exists():
            with stats_lock:
                stats["skipped"] += 1
            return

        # ✅ CRITICAL: Skip if failed too many times - prevents infinite retries
        if article.summarize_failed_count >= MAX_SUMMARIZE_FAILURES:
            with stats_lock:
                stats["skipped"] += 1
            return

        if not article.content or len(article.content) < 50:
            print(f"--- [SKIPPED] Article {article.id}: Content too short or empty.")
            with stats_lock:
                stats["skipped"] += 1
            return

        print(f"--- [PROCESSING] Summarizing article {article.id}: {article.title[:50]}...")
        full_content = summarize_and_translate_with_openai(
            article.content,
            article.title
        )

        # Split the first line as the title
        lines = full_content.split('\n')
        translated_title = lines[0].strip()
        
        # If the first line is empty or too short, fallback to original title
        if len(translated_title) < 5:
            translated_title = article.title

        Summary.objects.create(
            article=article,
            summary_text=full_content
        )

        article.is_summary = True
        article.title = translated_title
        article.summarize_failed_count = 0  # Reset on success
        article.last_summarize_attempt = timezone.now()
        article.save()

        print(f"+++ [SUCCESS] Article {article.id} summarized successfully.")
        with stats_lock:
            stats["processed"] += 1

    except Exception as e:
        print(f"Error processing article {article.id}: {e}")
        with stats_lock:
            stats["failed"] += 1
        
        # ✅ Track failure count to avoid infinite retries
        article.summarize_failed_count += 1
        article.last_summarize_attempt = timezone.now()
        article.save()

    finally:
        # Always release the article ID so re-runs work correctly
        with processing_lock:
            processing_ids.discard(article.id)


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

        # Get active topics for this user (topics linked to active channels)
        from apps.models import TelegramChannel, Classification
        active_topics = TelegramChannel.objects.filter(
            owner=user,
            is_active=True
        ).values_list('topic_id', flat=True).distinct()

        # Filter articles that have been classified into one of these active topics
        articles = list(
            Article.objects.filter(
                owner=user,
                is_summary=False,
                article_classifications__topic_id__in=active_topics
            ).distinct()
        )

        if not articles:
            self.stdout.write("No articles to summarize.")
            return

        self.stdout.write(f"Found {len(articles)} articles to process...")

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(process_article, a, stats) for a in articles]
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
