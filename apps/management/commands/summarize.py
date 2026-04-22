import os
import json

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


def summarize_and_translate_with_openai(text: str, title: str) -> tuple[str, str]:
    """
    OPTIMIZED: Single API call instead of 2 separate calls
    Returns JSON with both summary and translated title
    Saves 50% on API costs
    """
    with openai_semaphore:
        response = client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {
                    "role": "system",
                    "content": """Analyze the given article. Return a JSON object with exactly 2 fields:
1. "summary": A visually beautiful, well-structured summary in Uzbek (200-400 chars).
   - Use emojis for readability (e.g. 📌 for summary, 🔹 for points).
   - Use HTML bold tags (<b>text</b>) for key terms.
   - Use bullet points (•) for main highlights.
   - The tone should be informative and engaging for Uzbek readers.
   - Preserve natural Uzbek grammar (o', g', sh, ch).
2. "title": A catchy translation of the article title to Uzbek.

Return ONLY valid JSON, no markdown blocks or extra text."""
                },
                {
                    "role": "user",
                    "content": f"Article Title: {title}\n\nArticle Content: {text}"
                }
            ],
            temperature=0.2,
            max_output_tokens=350
        )

    response_text = extract_text(response)
    
    try:
        # Parse the JSON response
        result = json.loads(response_text)
        summary = result.get("summary", "")
        translated_title = result.get("title", title)
    except json.JSONDecodeError:
        # Fallback if JSON parsing fails
        summary = response_text[:200]
        translated_title = title
    
    return summary, translated_title


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
            with stats_lock:
                stats["skipped"] += 1
            return

        summary, translated_title = summarize_and_translate_with_openai(
            article.content,
            article.title
        )

        Summary.objects.create(
            article=article,
            summary_text=summary
        )

        article.is_summary = True
        article.title = translated_title
        article.summarize_failed_count = 0  # Reset on success
        article.last_summarize_attempt = timezone.now()
        article.save()

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

        start = datetime.datetime.now()

        # Reset stats per run (not global state)
        stats = {"processed": 0, "failed": 0, "skipped": 0}

        articles = list(
            Article.objects.filter(
                owner=user,
                is_summary=False
            )
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
