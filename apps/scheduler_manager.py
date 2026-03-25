import threading
import time
import logging
from django.core.management import call_command

logger = logging.getLogger(__name__)

_running_users = set()
_lock = threading.Lock()


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


def _user_pipeline_loop(user_id: int):
    try:
        while True:
            logger.info(f"⚡ [user={user_id}] Running pipeline...")

            try:
                call_command('crawl_news', user_id=user_id)
                logger.info(f"✅ [user={user_id}] Crawl done")
            except Exception as e:
                logger.error(f"❌ [user={user_id}] Crawl failed: {e}")

            try:
                call_command('summarize', user_id=user_id)
                logger.info(f"✅ [user={user_id}] Summarize done")
            except Exception as e:
                logger.error(f"❌ [user={user_id}] Summarize failed: {e}")

            try:
                call_command('classify_articles', user_id=user_id)
                logger.info(f"✅ [user={user_id}] Classify done")
            except Exception as e:
                logger.error(f"❌ [user={user_id}] Classify failed: {e}")

            logger.info(f"🏁 [user={user_id}] Pipeline done. Sleeping 1 hour...")
            time.sleep(3600)

    except Exception as e:
        logger.error(f"💥 [user={user_id}] Pipeline thread crashed: {e}")
    finally:
        with _lock:
            _running_users.discard(user_id)
        logger.warning(f"⚠️ [user={user_id}] Pipeline thread stopped")