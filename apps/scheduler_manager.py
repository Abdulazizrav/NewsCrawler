import threading
import time
import logging
import subprocess
from django.db import close_old_connections

logger = logging.getLogger(__name__)

_running_users = set()
_lock = threading.Lock()
_scheduler_started = False


def start_user_pipeline(user_id: int):
    with _lock:
        if user_id in _running_users:
            logger.info(f"Pipeline already running for user {user_id}")
            return
        _running_users.add(user_id)

    thread = threading.Thread(
        target=_user_pipeline_loop,
        args=(user_id,),
        daemon=True,
        name=f"pipeline-user-{user_id}"
    )
    thread.start()
    logger.info(f"🚀 Started pipeline thread for user {user_id}")


def start_scheduled_send_checker():
    global _scheduler_started
    with _lock:
        if _scheduler_started:
            logger.info("Scheduler already running, skipping")
            return
        _scheduler_started = True

    logger.info("⏰ Starting scheduled send checker thread...")
    thread = threading.Thread(
        target=_scheduled_send_loop,
        daemon=True,
        name="scheduled-send-checker"
    )
    thread.start()
    logger.info("⏰ Scheduled send checker started successfully")


def _scheduled_send_loop():
    while True:
        try:
            close_old_connections()  # ✅ reuse connections
            from apps.models.scheduled_send import ScheduledSend
            from django.utils import timezone
            now = timezone.now()
            pending = ScheduledSend.objects.filter(is_sent=False, scheduled_time__lte=now)
            for scheduled in pending:
                logger.info(f"⏰ Firing scheduled send id={scheduled.id} for user={scheduled.user_id}")
                subprocess.Popen([
                    'python', 'manage.py', 'send_to_telegram',
                    f'--user_id={scheduled.user_id}',
                    f'--summary_ids={scheduled.summary_ids}',
                    f'--channel_ids={scheduled.channel_ids}',
                ])
                scheduled.is_sent = True
                scheduled.save()
        except Exception as e:
            logger.error(f"❌ Scheduled send checker error: {e}")
        finally:
            close_old_connections()  # ✅ always release after check

        time.sleep(60)


def _user_pipeline_loop(user_id: int):
    try:
        while True:
            logger.info(f"⚡ [user={user_id}] Running pipeline...")

            # ✅ Use subprocess — each command is isolated, no shared DB connections
            _run_command(['python', 'manage.py', 'crawl_news', f'--user_id={user_id}'], user_id, 'Crawl')
            _run_command(['python', 'manage.py', 'summarize', f'--user_id={user_id}'], user_id, 'Summarize')
            _run_command(['python', 'manage.py', 'classify_articles', f'--user_id={user_id}'], user_id, 'Classify')

            logger.info(f"🏁 [user={user_id}] Pipeline done. Sleeping 1 hour...")
            time.sleep(3600)

    except Exception as e:
        logger.error(f"💥 [user={user_id}] Pipeline thread crashed: {e}")
    finally:
        with _lock:
            _running_users.discard(user_id)
        logger.warning(f"⚠️ [user={user_id}] Pipeline thread stopped")


def _run_command(command: list, user_id: int, name: str):
    try:
        # ✅ subprocess.run waits for completion — sequential, no parallel DB connections
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode == 0:
            logger.info(f"✅ [user={user_id}] {name} done")
        else:
            logger.error(f"❌ [user={user_id}] {name} failed:\n{result.stderr}")
    except Exception as e:
        logger.error(f"❌ [user={user_id}] {name} exception: {e}")