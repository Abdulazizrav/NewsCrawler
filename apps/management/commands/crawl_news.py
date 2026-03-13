from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from concurrent.futures import ThreadPoolExecutor
from ...scripts.crawlers import (
    crawl_from_truck,
    crawl_with_rss,
    crawl_from_rss_http,
    crawl_from_qalampir,
    crawl_from_guardian,


)

import datetime


class Command(BaseCommand):
    help = "Run news crawler for specific user"

    def add_arguments(self, parser):
        parser.add_argument(
            '--user_id',
            type=int,
            required=True,
            help="User ID for tenant isolation"
        )

    def handle(self, *args, **options):
        user_id = options['user_id']

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR("User not found"))
            return

        self.stdout.write(
            self.style.SUCCESS(f"Starting crawler for user: {user.username}")
        )

        start = datetime.datetime.now()


        # Run crawlers in parallel
        with ThreadPoolExecutor(max_workers=5) as executor:
            executor.submit(run_all_crawlers,  user)

        end = datetime.datetime.now()
        self.stdout.write(
            self.style.SUCCESS(f"Crawler finished in {end - start}")
        )


# =========================
# RUN ALL CRAWLERS PER TOPIC
# =========================

def run_all_crawlers(user):
    """
    Runs all crawler sources for a given topic and user
    """

    try:
        #crawl_from_truck(user)
        crawl_with_rss(user)
        crawl_from_guardian(user)
        crawl_from_rss_http(user)
        crawl_from_qalampir(user)
        # crawl_from_guardian(topic, user)
        # crawl_from_qalampir(topic, user)
        # crawl_from_sputnik(topic, user)

    except Exception as e:
        print(f"Error: {e}")