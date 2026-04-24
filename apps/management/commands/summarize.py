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
1. "summary": A structured, visually beautiful summary in Uzbek.
   CRITICAL RULES for vertical spacing:
   - Use double newlines (\\n\\n) to separate the introduction from the highlights.
   - Every bullet point (•) MUST start on a NEW line.
   - Use emojis (📌, 🔹) to mark sections.
   - The summary should be easy to scan and professional.

   EXAMPLE STRUCTURE:
   📌 [Kirish qismi...]
   
   🔹 Asosiy ma'lumotlar:
   • [Birinchi fakt]
   • [Ikkinchi fakt]

2. "title": A catchy translation of the article title to Uzbek.

CRITICAL: Return ONLY a raw JSON object. 
DO NOT use ```json or any markdown blocks.
DO NOT include any text before or after the JSON.
Valid JSON format only."""
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
    cleaned_text = clean_json_response(response_text)
    
    try:
        # Parse the JSON response
        result = json.loads(cleaned_text)
        summary = result.get("summary", "")
        translated_title = result.get("title", title)
        
    except json.JSONDecodeError:
        print(f"!!! [ERROR] JSON parsing failed for article. Raw response: {response_text[:100]}...")
        # Fallback: Try to strip common JSON noise manually if regex failed
        summary = cleaned_text.replace('{"summary":', '').replace('"title":', '').replace('}', '').replace('{', '').strip()
        # Remove trailing title part if it's there
        if '"' in summary:
            parts = summary.split('","')
            summary = parts[0].strip('"')
            if len(parts) > 1:
                translated_title = parts[1].split('": "')[-1].strip('"')
            else:
                translated_title = title
        else:
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
            print(f"--- [SKIPPED] Article {article.id}: Content too short or empty.")
            with stats_lock:
                stats["skipped"] += 1
            return

        print(f"--- [PROCESSING] Summarizing article {article.id}: {article.title[:50]}...")
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
