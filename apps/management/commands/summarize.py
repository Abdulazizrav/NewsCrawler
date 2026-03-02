import os

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from dotenv import load_dotenv

from apps.models import Summary, Article
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, Semaphore
import datetime

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
stats_lock = Lock()
openai_semaphore = Semaphore(5)

stats = {
    "processed": 0,
    "failed": 0,
    "skipped": 0,
}


def extract_text(response):
    try:
        return response.output[0].content[0].text.strip()
    except Exception:
        return ""


def summarize_and_translate_with_openai(text: str, title: str) -> tuple[str, str]:
    with openai_semaphore:
        summary_response = client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {"role": "system", "content": "Summarize in 2-4 sentences in Uzbek."},
                {"role": "user", "content": text}
            ],
            temperature=0.2,
            max_output_tokens=250
        )

        title_response = client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {
                    "role": "system",
                    "content": "Translate the given title to Uzbek. Return only the translated title, nothing else."
                },
                {"role": "user", "content": title}
            ],
            temperature=0.1,
            max_output_tokens=100
        )

    return extract_text(summary_response), extract_text(title_response)


def process_article(article):
    if article.is_summary or Summary.objects.filter(article=article).exists():
        with stats_lock:
            stats["skipped"] += 1
        return

    if not article.content or len(article.content) < 50:
        with stats_lock:
            stats["skipped"] += 1
        return

    try:
        summary, translated_title = summarize_and_translate_with_openai(
            article.content,
            article.title
        )

        Summary.objects.create(
            article=article,
            summary_text=summary
        )

        article.is_summary = True
        article.translated_title = translated_title  # adjust field name if different in your model
        article.save()

        with stats_lock:
            stats["processed"] += 1

    except Exception as e:
        print(f"Error processing article {article.id}: {e}")
        with stats_lock:
            stats["failed"] += 1


class Command(BaseCommand):
    help = "Summarize articles and translate titles for a specific user"

    def add_arguments(self, parser):
        parser.add_argument('--user_id', type=int, required=True)

    def handle(self, *args, **options):
        user = User.objects.get(id=options["user_id"])

        start = datetime.datetime.now()

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
            futures = [executor.submit(process_article, a) for a in articles]
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