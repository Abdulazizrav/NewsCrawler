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
1. "summary": A concise, high-value summary in Uzbek.
   CRITICAL QUALITY RULES:
   - ZERO REPETITION: Do not repeat the same point in the introduction and the bullet points.
   - NO TITLE REPETITION: Do not start the summary by repeating the title.
   - CONCISE INTRO: The introduction (📌) must be exactly 1 or 2 short, punchy sentences.
   - FACTUAL BULLETS: Every bullet point (•) must provide unique facts, arguments, or data found in the article. 
   - Each bullet point MUST contain new information not previously mentioned in the summary.
   
   FORMATTING RULES:
   - Use double newlines (\\n\\n) to separate the introduction from the details.
   - Every bullet point (•) MUST start on a NEW line.
   - Use emojis (📌, 🔹) to mark sections.
   - The output must be professional and easy to scan.

   EXAMPLE STRUCTURE:
   📌 [Short 1-2 sentence overview...]
   
   🔹 Muhim tafsilotlar:
   • [Unique fact or argument A]
   • [Unique fact or argument B]

2. "title": A catchy, translated title in Uzbek.

CRITICAL: Return ONLY raw JSON. No markdown blocks."""
                },
                {
                    "role": "user",
                    "content": f"Article Title: {title}\n\nArticle Content: {text}"
                }
            ],
            temperature=0.2,
            max_output_tokens=1000
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
        
        # Robust fallback: Use regex to extract fields when JSON is malformed (e.g., unescaped newlines or truncation)
        summary = ""
        translated_title = title
        
        # Extract summary
        summary_match = re.search(r'"summary"\s*:\s*"(.*?)"\s*(?:,\s*"title"|\}$)', cleaned_text, re.DOTALL)
        if summary_match:
            summary = summary_match.group(1).replace('\\n', '\n').replace('\\"', '"')
        else:
            # Absolute fallback if regex fails
            clean_str = cleaned_text.strip()
            if clean_str.startswith('{'): clean_str = clean_str[1:]
            if clean_str.endswith('}'): clean_str = clean_str[:-1]
            clean_str = re.sub(r'^"summary"\s*:\s*"', '', clean_str.strip())
            
            if '"title"' in clean_str:
                parts = re.split(r'",?\s*"title"\s*:\s*"', clean_str)
                summary = parts[0]
                if len(parts) > 1:
                    translated_title = parts[1].rstrip('"')
            else:
                summary = clean_str.rstrip('"')
            
            summary = summary.replace('\\n', '\n').replace('\\"', '"')

        # Extract title if not caught by manual split
        if translated_title == title:
            title_match = re.search(r'"title"\s*:\s*"(.*?)"', cleaned_text, re.DOTALL)
            if title_match:
                translated_title = title_match.group(1).replace('\\"', '"')
    
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
