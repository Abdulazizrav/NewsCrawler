import asyncio
import logging
import os
import sys
from datetime import timedelta

from aiogram import Dispatcher, Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BufferedInputFile
from aiogram.enums import ParseMode

from asgiref.sync import sync_to_async
from django.core.management import BaseCommand
from django.utils import timezone

from apps.models import Summary, TelegramDelivery

from dotenv import load_dotenv
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

dp = Dispatcher()

DELAY_BETWEEN_MESSAGES = 2


async def send_summaries_to_channels(bot: Bot, user_id: int, summary_ids: list = None, channel_ids: list = None):
    """
    If summary_ids is provided, only those summaries are sent.
    If channel_ids is provided, only those channels are used.
    Otherwise falls back to last-hour / all-active-channels behaviour.
    """
    if summary_ids:
        # ✅ Send only the explicitly selected summaries
        summaries = await sync_to_async(list)(
            Summary.objects.filter(
                pk__in=summary_ids,
                article__owner_id=user_id  # enforce ownership
            )
            .select_related('article')
            .prefetch_related('article__article_classifications__topic')
        )
    else:
        # ✅ Default: last hour
        last_hour = timezone.now() - timedelta(hours=1)
        summaries = await sync_to_async(list)(
            Summary.objects.filter(
                created_date__gte=last_hour,
                article__owner_id=user_id
            )
            .select_related('article')
            .prefetch_related('article__article_classifications__topic')
        )

    if not summaries:
        logging.info("No summaries to send for this user.")
        return 0, 0

    sent_count = 0
    error_count = 0

    for summary in summaries:
        try:
            def get_classification():
                return summary.article.article_classifications.select_related('topic').first()

            classification = await sync_to_async(get_classification)()

            if not classification or not classification.topic:
                logging.warning(f"Summary {summary.id} skipped — no classification or topic")
                error_count += 1
                continue

            topic = classification.topic

            # Match channels by topic NAME (not FK) so superadmin topics
            # link correctly to channel admin channels even if topic objects differ
            from apps.models import TelegramChannel
            channel_qs = TelegramChannel.objects.filter(
                is_active=True,
                owner_id=user_id,
                topic__name=topic.name,  # match by name, not by id
            )
            if channel_ids:
                channel_qs = channel_qs.filter(pk__in=channel_ids)

            channels = await sync_to_async(list)(channel_qs)

            if not channels:
                continue

            caption = (
                f"<b>{summary.article.title}</b>\n\n"
                f"{summary.summary_text}\n\n"
                f'<a href="{summary.article.url}">Batafsil</a>'
            )

            def get_image():
                return summary.article.images.first()

            image_obj = await sync_to_async(get_image)()

            for channel in channels:

                def check_already_sent():
                    return TelegramDelivery.objects.filter(
                        summary=summary,
                        telegram_channel=channel,
                        status="sent"
                    ).exists()

                already_sent = await sync_to_async(check_already_sent)()
                if already_sent:
                    continue

                if channel.balance < channel.price_per_message:
                    continue

                try:
                    if image_obj and image_obj.image:
                        input_file = BufferedInputFile(
                            file=image_obj.image,
                            filename="article_image.jpg"
                        )
                        sent_message = await bot.send_photo(
                            chat_id=channel.channel_id,
                            photo=input_file,
                            caption=caption,
                            parse_mode=ParseMode.HTML
                        )
                    else:
                        sent_message = await bot.send_message(
                            chat_id=channel.channel_id,
                            text=caption,
                            parse_mode=ParseMode.HTML,
                            disable_web_page_preview=True
                        )

                    await asyncio.sleep(DELAY_BETWEEN_MESSAGES)

                    await sync_to_async(TelegramDelivery.objects.create)(
                        summary=summary,
                        telegram_channel=channel,
                        message_id=sent_message.message_id,
                        sent_date=timezone.now(),
                        status="sent",
                        cost_charged=channel.price_per_message,
                    )

                    channel.balance -= channel.price_per_message
                    await sync_to_async(channel.save)()

                    sent_count += 1

                except Exception as send_err:
                    logging.error(f"Failed to send to channel {channel.id}: {send_err}")
                    error_count += 1

                    await sync_to_async(TelegramDelivery.objects.create)(
                        summary=summary,
                        telegram_channel=channel,
                        message_id=0,
                        sent_date=timezone.now(),
                        status="failed",
                        cost_charged=0
                    )

        except Exception as e:
            logging.error(f"Error processing summary {summary.id}: {e}")
            error_count += 1

    return sent_count, error_count


async def main(user_id: int, summary_ids: list = None, channel_ids: list = None):
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    logging.info(f"Telegram sending started for user_id={user_id}, summary_ids={summary_ids}, channel_ids={channel_ids}")
    try:
        sent_count, error_count = await send_summaries_to_channels(bot, user_id, summary_ids, channel_ids)
        logging.info(f"Finished. Sent: {sent_count}, Errors: {error_count}")
    finally:
        await bot.session.close()


class Command(BaseCommand):
    help = 'Send Telegram summaries (multi-tenant, supports --summary_ids)'

    def add_arguments(self, parser):
        parser.add_argument('--user_id', type=int, required=True)
        parser.add_argument(
            '--summary_ids',
            type=str,
            default=None,
            help='Comma-separated summary IDs (optional). If omitted, sends last hour.'
        )
        parser.add_argument(
            '--channel_ids',
            type=str,
            default=None,
            help='Comma-separated channel IDs to send to (optional). If omitted, uses all active channels.'
        )

    def handle(self, *args, **options):
        user_id  = options["user_id"]
        raw_ids  = options.get("summary_ids")
        raw_cids = options.get("channel_ids")

        summary_ids = None
        if raw_ids:
            try:
                summary_ids = [int(i.strip()) for i in raw_ids.split(',') if i.strip()]
            except ValueError:
                self.stdout.write(self.style.ERROR('Invalid --summary_ids format.'))
                return

        channel_ids = None
        if raw_cids:
            try:
                channel_ids = [int(i.strip()) for i in raw_cids.split(',') if i.strip()]
            except ValueError:
                self.stdout.write(self.style.ERROR('Invalid --channel_ids format.'))
                return

        logging.basicConfig(
            level=logging.INFO,
            stream=sys.stdout,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'Starting Telegram for user_id={user_id}'
                + (f', summary_ids={summary_ids}' if summary_ids else ' (last hour)')
            )
        )

        try:
            asyncio.run(main(user_id, summary_ids, channel_ids))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {e}'))