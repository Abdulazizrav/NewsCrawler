import os

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from dotenv import load_dotenv
from openai import OpenAI
from apps.models import Classification, Topic, Article, Summary
import datetime
import time

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def extract_text(response):
    try:
        return response.output[0].content[0].text.strip()
    except Exception as e:
        return f"Error: {e}"


class Command(BaseCommand):
    help = "Classify summarized articles for a specific user"

    def add_arguments(self, parser):
        parser.add_argument('--user_id', type=int, required=True)

    def handle(self, *args, **options):
        print("Classification command started!")
        user = User.objects.get(id=options["user_id"])

        start = datetime.datetime.now()

        topics = Topic.objects.filter(owner=user)
        topic_names = list(topics.values_list("name", flat=True))
        print(f"User topics: {topic_names}")

        if not topic_names:
            self.stdout.write("No topics found for this user.")
            return

        articles = Article.objects.filter(
            owner=user,
            is_summary=True
        )

        if not articles.exists():
            self.stdout.write("No summarized articles found for this user.")
            return

        self.stdout.write(f"Found {articles.count()} articles to classify...")

        processed = 0
        skipped = 0
        failed = 0

        for article in articles:
            # Skip if already classified
            if Classification.objects.filter(article=article).exists():
                print(f"Article {article.id} already classified, skipping.")
                skipped += 1
                continue

            summary = Summary.objects.filter(article=article).first()
            if not summary or not summary.summary_text:
                print(f"No summary found for article {article.id}, skipping.")
                skipped += 1
                continue

            text = summary.summary_text
            print(f"Classifying article {article.id}: {text[:80]}...")

            try:
                response = client.responses.create(
                    model="gpt-4.1-mini",
                    input=[
                        {
                            "role": "system",
                            "content": (
                                f"You are a classifier. Choose exactly one topic from this list and respond with "
                                f"ONLY that topic name — no explanation, no punctuation, no extra text:\n"
                                f"{', '.join(topic_names)}"
                            )
                        },
                        {
                            "role": "user",
                            "content": text
                        }
                    ],
                    temperature=0.0,
                    max_output_tokens=50
                )

                topic_name = extract_text(response).strip().strip(".,!?\"'")
                print(f"GPT returned topic: '{topic_name}'")

                # Try exact match first (case-insensitive)
                topic = topics.filter(name__iexact=topic_name).first()

                # Fallback: check if any known topic name is contained within the response
                if not topic:
                    for t in topics:
                        if t.name.lower() in topic_name.lower():
                            topic = t
                            print(f"Matched via fallback: '{t.name}'")
                            break

                if topic:
                    Classification.objects.create(
                        article=article,
                        topic=topic
                    )
                    print(f"Article {article.id} classified as '{topic.name}'")
                    processed += 1
                else:
                    print(f"Could not match topic '{topic_name}' to any known topic for article {article.id}")
                    failed += 1

            except Exception as e:
                print(f"Error classifying article {article.id}: {e}")
                failed += 1

            time.sleep(0.3)

        duration = datetime.datetime.now() - start

        self.stdout.write(
            self.style.SUCCESS(
                f"Done in {duration} | "
                f"Classified: {processed} | "
                f"Failed/Unmatched: {failed} | "
                f"Skipped: {skipped}"
            )
        )