import sys
import os
import threading
import time
import logging
import subprocess

logger = logging.getLogger(__name__)

_running_users = set()
_lock = threading.Lock()
_scheduler_started = False


def start_all_pipelines():
    thread = threading.Thread(
        target=_bootstrap_pipelines,
        daemon=True,
        name="pipeline-bootstrap"
    )
    thread.start()


def _bootstrap_pipelines():
    try:
        from django.db import close_old_connections
        close_old_connections()
        from django.contrib.auth import get_user_model
        from apps.permissions import is_superadmin
        User = get_user_model()
        users = list(User.objects.filter(is_active=True))
        close_old_connections()
        for user in users:
            if not is_superadmin(user):
                start_user_pipeline(user.id)
                logger.info(f"✅ Pipeline started for user {user.id}")
    except Exception as e:
        logger.warning(f"Could not bootstrap pipelines: {e}")
    finally:
        try:
            from django.db import close_old_connections
            close_old_connections()
        except Exception:
            pass


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
    time.sleep(15)
    while True:
        try:
            from django.db import close_old_connections
            close_old_connections()
            from apps.models.scheduled_send import ScheduledSend
            from django.utils import timezone
            now = timezone.now()
            pending = list(ScheduledSend.objects.filter(is_sent=False, scheduled_time__lte=now))
            for scheduled in pending:
                logger.info(f"⏰ Firing scheduled send id={scheduled.id} for user={scheduled.user_id}")
                subprocess.Popen([
                    sys.executable, 'manage.py', 'send_to_telegram',  # ✅
                    f'--user_id={scheduled.user_id}',
                    f'--summary_ids={scheduled.summary_ids}',
                    f'--channel_ids={scheduled.channel_ids}',
                ])
                scheduled.is_sent = True
                scheduled.save()
        except Exception as e:
            logger.error(f"❌ Scheduled send checker error: {e}")
        finally:
            try:
                from django.db import close_old_connections
                close_old_connections()
            except Exception:
                pass
        time.sleep(300)


def _user_pipeline_loop(user_id: int):
    try:
        time.sleep(60)
        while True:
            logger.info(f"⚡ [user={user_id}] Running pipeline...")
            _run_command([sys.executable, 'manage.py', 'crawl_news', f'--user_id={user_id}'], user_id, 'Crawl')  # ✅
            time.sleep(10)
            _run_command([sys.executable, 'manage.py', 'summarize', f'--user_id={user_id}'], user_id, 'Summarize')  # ✅
            time.sleep(10)
            _run_command([sys.executable, 'manage.py', 'classify_articles', f'--user_id={user_id}'], user_id, 'Classify')  # ✅
            time.sleep(10)
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
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # ✅ project root
        )
        if result.returncode == 0:
            logger.info(f"✅ [user={user_id}] {name} done")
        else:
            logger.error(f"❌ [user={user_id}] {name} failed:\n{result.stderr}")
    except Exception as e:
        logger.error(f"❌ [user={user_id}] {name} exception: {e}")