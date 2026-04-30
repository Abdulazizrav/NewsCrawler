import os

from django.db import close_old_connections
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
        close_old_connections()  # ✅ add this
        user = User.objects.get(id=options["user_id"])
        print(f"=== [START] Classification started for user: {user.username} (ID: {user.id})")

        start = datetime.datetime.now()

        topics = Topic.objects.filter(owner__is_staff=True)
        topic_names = list(topics.values_list("name", flat=True))
        print(f"User topics: {topic_names}")

        if not topic_names:
            self.stdout.write("No topics found for this user.")
            return

        articles = Article.objects.filter(
            owner=user,
            is_summary=False
        )

        if not articles.exists():
            self.stdout.write("No articles found for classification.")
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

            # Use Title and Content for classification as summary is not generated yet
            text = f"TITLE: {article.title}\n\nCONTENT: {article.content[:2000]}" # Limit content length
            print(f"Classifying article {article.id}: {article.title[:80]}...")

            try:
                response = client.chat.completions.create( # Using chat.completions instead of responses
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                f"You are a professional news classifier. Analyze the article and choose exactly one topic from this list:\n"
                                f"{', '.join(topic_names)}\n\n"
                                f"If the article DOES NOT fit any of these topics, respond with ONLY the word 'None'.\n"
                                f"Otherwise, respond with ONLY the exact topic name — no explanation, no punctuation, no extra text."
                            )
                        },
                        {
                            "role": "user",
                            "content": text
                        }
                    ],
                    temperature=0.0,
                    max_tokens=50
                )

                topic_name = response.choices[0].message.content.strip().strip(".,!?\"'")
                print(f"GPT returned: '{topic_name}'")

                if topic_name.lower() == 'none' or topic_name.lower() == 'not relevant':
                    Classification.objects.create(
                        article=article,
                        topic=None
                    )
                    print(f"--- [NONE] Article {article.id} marked as Not Relevant")
                    processed += 1
                    continue

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
                    print(f"+++ [SUCCESS] Article {article.id} classified as '{topic.name}'")
                    processed += 1
                else:
                    # If AI returned something that isn't a topic and isn't "None", we mark as None to avoid re-runs
                    Classification.objects.create(
                        article=article,
                        topic=None
                    )
                    print(f"!!! [UNMATCHED] '{topic_name}' did not match topics. Marked as None.")
                    processed += 1

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