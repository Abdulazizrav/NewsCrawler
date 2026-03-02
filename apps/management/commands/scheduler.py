import os
import django
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django.core.management import BaseCommand

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from apps.management.commands.crawl_news import run as run_crawl
from apps.management.commands.summarize import run as run_summarize
from apps.management.commands.classify_articles import run as run_classify
from django.core.management import call_command

scheduler = BackgroundScheduler()


def crawl_task():
    logger.info("🔄 Starting crawl...")
    try:
        run_crawl()
        logger.info("✅ Crawl completed")
    except Exception as e:
        logger.error(f"❌ Crawl failed: {e}")


def summarize_task():
    logger.info("📝 Starting summarize...")
    try:
        run_summarize()
        logger.info("✅ Summarize completed")
    except Exception as e:
        logger.error(f"❌ Summarize failed: {e}")


def classify_task():
    logger.info("🏷️ Starting classify...")
    try:
        run_classify()
        logger.info("✅ Classify completed")
    except Exception as e:
        logger.error(f"❌ Classify failed: {e}")


def send_task():
    logger.info("📤 Starting send to telegram...")
    try:
        call_command('send_to_telegram')
        logger.info("✅ Send completed")
    except Exception as e:
        logger.error(f"❌ Send failed: {e}")


def start_scheduler():
    """Start all scheduled tasks every 2 hours"""

    scheduler.add_job(
        crawl_task,
        trigger=CronTrigger(hour='*/2', minute=0),
        id='crawl',
        name='Crawl - Every 2 hours',
        replace_existing=True
    )

    scheduler.add_job(
        summarize_task,
        trigger=CronTrigger(hour='*/2', minute=0),
        id='summarize',
        name='Summarize - Every 2 hours',
        replace_existing=True
    )

    scheduler.add_job(
        classify_task,
        trigger=CronTrigger(hour='*/2', minute=0),
        id='classify',
        name='Classify - Every 2 hours',
        replace_existing=True
    )

    scheduler.add_job(
        send_task,
        trigger=CronTrigger(hour='*/2', minute=0),
        id='send',
        name='Send - Every 2 hours',
        replace_existing=True
    )

    scheduler.start()
    logger.info("✅ Scheduler started with 4 jobs (every 2 hours)")

    for job in scheduler.get_jobs():
        logger.info(f"📅 {job.name}")


class Command(BaseCommand):
    help = 'Start the scheduler'

    def handle(self, *args, **options):
        logger.info("🚀 Starting scheduler...")
        try:
            start_scheduler()
            while True:
                pass
        except KeyboardInterrupt:
            logger.warning("⚠️ Scheduler stopped")
            scheduler.shutdown()