from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.management import call_command
from django.db.models import Count, Sum, Q
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import threading
import subprocess
from django.views.decorators.http import require_POST

from apps.models import Article, TelegramDelivery, TelegramChannel, Summary, Classification, Topic


@login_required(login_url='/admin/login/')
def dashboard_home(request):
    """Main dashboard with overview stats"""
    today = timezone.now().date()

    # ===== USER FILTER =====
    user_articles = Article.objects.filter(owner=request.user)
    user_channels = TelegramChannel.objects.filter(owner=request.user)
    user_deliveries = TelegramDelivery.objects.filter(
        telegram_channel__owner=request.user
    )

    # ===== ARTICLE STATS =====
    total_articles = user_articles.count()

    try:
        articles_today = user_articles.filter(
            published_date__date=today
        ).count()
    except:
        articles_today = user_articles.filter(
            published_date__startswith=str(today)
        ).count()

    total_summaries = user_articles.filter(is_summary=True).count()
    pending_summaries = user_articles.filter(is_summary=False).count()

    # ===== CHANNEL STATS =====
    active_channels = user_channels.filter(is_active=True).count()
    total_channels = user_channels.count()

    # ===== DELIVERY STATS =====
    try:
        messages_today = user_deliveries.filter(
            sent_date__date=today
        ).count()

        revenue_today = user_deliveries.filter(
            sent_date__date=today,
            status='sent'
        ).aggregate(total=Sum('cost_charged'))['total'] or Decimal('0.00')

    except:
        messages_today = user_deliveries.filter(
            sent_date__startswith=str(today)
        ).count()

        revenue_today = user_deliveries.filter(
            sent_date__startswith=str(today),
            status='sent'
        ).aggregate(total=Sum('cost_charged'))['total'] or Decimal('0.00')

    total_delivered = user_deliveries.filter(status='sent').count()

    # ===== LOW BALANCE CHANNELS =====
    low_balance_channels = user_channels.filter(
        balance__lt=10,
        is_active=True
    ).order_by('balance')[:5]

    # ===== RECENT ARTICLES =====
    recent_articles = user_articles.order_by('-published_date')[:5]

    for article in recent_articles:
        article.has_summary = Summary.objects.filter(
            article=article
        ).exists()

    context = {
        'total_articles': total_articles,
        'articles_today': articles_today,
        'total_summaries': total_summaries,
        'pending_summaries': pending_summaries,
        'active_channels': active_channels,
        'total_channels': total_channels,
        'messages_today': messages_today,
        'total_delivered': total_delivered,
        'revenue_today': revenue_today,
        'low_balance_channels': low_balance_channels,
        'recent_articles': recent_articles,
    }

    return render(request, 'home.html', context)

@login_required(login_url='/admin/login/')
def article_list(request):
    """List user articles with filters"""

    # ✅ Always filter by owner
    articles = Article.objects.filter(
        owner=request.user
    ).order_by('-published_date')

    # Filters
    source = request.GET.get('source')
    has_summary = request.GET.get('has_summary')
    search = request.GET.get('search')

    if source:
        articles = articles.filter(source__icontains=source)

    # ✅ Important: only summaries of THIS USER
    user_summaries = Summary.objects.filter(
        article__owner=request.user
    ).values_list('article_id', flat=True)

    if has_summary == 'yes':
        articles = articles.filter(id__in=user_summaries)

    elif has_summary == 'no':
        articles = articles.exclude(id__in=user_summaries)

    if search:
        articles = articles.filter(
            Q(title__icontains=search) |
            Q(content__icontains=search)
        )

    # Efficient summary check
    article_ids_with_summaries = set(user_summaries)

    for article in articles:
        article.has_summary = article.id in article_ids_with_summaries

    from django.core.paginator import Paginator
    paginator = Paginator(articles, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # ✅ Only this user's sources
    sources = Article.objects.filter(
        owner=request.user
    ).values_list('source', flat=True).distinct()

    context = {
        'page_obj': page_obj,
        'sources': sources,
        'current_source': source,
        'current_has_summary': has_summary,
        'current_search': search,
    }

    return render(request, 'articles.html', context)


@login_required(login_url='/admin/login/')
def article_detail(request, pk):
    # ✅ Only allow access to user's own article
    article = get_object_or_404(
        Article,
        pk=pk,
        owner=request.user
    )

    # Summary automatically belongs to that article
    summary = Summary.objects.filter(
        article=article
    ).first()

    # Classifications linked to this article
    classifications = Classification.objects.filter(
        article=article
    ).select_related('topic')

    context = {
        'article': article,
        'summary': summary,
        'classifications': classifications,
    }

    return render(request, 'article_detail.html', context)

@login_required(login_url='/admin/login/')
def article_delete(request, pk):
    if request.method == 'POST':
        article = get_object_or_404(
            Article,
            pk=pk,
            owner=request.user  # ✅ enforce ownership
        )

        article.delete()
        messages.success(request, 'Article deleted successfully!')
        return redirect('dashboard:article_list')

    return redirect('dashboard:article_list')


@login_required(login_url='/admin/login/')
def summary_list(request):
    """List user summaries only"""

    summaries = Summary.objects.filter(
        article__owner=request.user  # ✅ filter via article owner
    ).select_related('article').order_by('-created_date')

    from django.core.paginator import Paginator
    paginator = Paginator(summaries, 30)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {'page_obj': page_obj}
    return render(request, 'summaries.html', context)


@login_required(login_url='/admin/login/')
def classification_list(request):
    """List user classifications only"""

    classifications = Classification.objects.filter(
        article__owner=request.user  # ✅ enforce ownership
    ).select_related('article', 'topic').order_by('-id')

    topic_filter = request.GET.get('topic')

    if topic_filter:
        # Make sure topic also belongs to this user
        classifications = classifications.filter(
            topic_id=topic_filter,
            topic__owner=request.user
        )

    from django.core.paginator import Paginator
    paginator = Paginator(classifications, 30)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # ✅ Only user's topics
    topics = Topic.objects.filter(owner=request.user)

    context = {
        'page_obj': page_obj,
        'topics': topics,
        'current_topic': topic_filter,
    }

    return render(request, 'classifications.html', context)


# ==================== BOBURBEK SECTION ====================
@login_required(login_url='/admin/login/')
def topic_list(request):
    """List user topics only"""

    # ✅ Only user's topics
    topics = Topic.objects.filter(owner=request.user)

    for topic in topics:
        # ✅ Count only user's article classifications
        topic.article_count = Classification.objects.filter(
            topic=topic,
            article__owner=request.user
        ).count()

        # ✅ Count only user's channels
        topic.channel_count = TelegramChannel.objects.filter(
            topic=topic,
            owner=request.user
        ).count()

        topic.keyword_list = [
            k.strip() for k in topic.keywords.split(',')
        ] if topic.keywords else []

    context = {'topics': topics}
    return render(request, 'topics.html', context)


@login_required(login_url='/admin/login/')
def topic_add(request):
    """Add new topic"""

    if request.method == 'POST':
        name = request.POST.get('name')
        keywords = request.POST.get('keywords')

        Topic.objects.create(
            owner=request.user,  # ✅ assign owner
            name=name,
            keywords=keywords
        )

        messages.success(request, f'Topic "{name}" added!')
        return redirect('dashboard:topic_list')

    return render(request, 'topic_form.html', {'action': 'Add'})


@login_required(login_url='/admin/login/')
def topic_edit(request, pk):
    """Edit topic"""

    topic = get_object_or_404(
        Topic,
        pk=pk,
        owner=request.user  # ✅ enforce ownership
    )

    if request.method == 'POST':
        topic.name = request.POST.get('name')
        topic.keywords = request.POST.get('keywords')
        topic.save()

        messages.success(request, f'Topic "{topic.name}" updated!')
        return redirect('dashboard:topic_list')

    context = {'topic': topic, 'action': 'Edit'}
    return render(request, 'topic_form.html', context)


@login_required(login_url='/admin/login/')
def topic_delete(request, pk):
    """Delete topic"""

    if request.method == 'POST':
        topic = get_object_or_404(
            Topic,
            pk=pk,
            owner=request.user  # ✅ enforce ownership
        )

        name = topic.name
        topic.delete()

        messages.success(request, f'Topic "{name}" deleted!')

    return redirect('dashboard:topic_list')


from django.db.models import Count, Sum, Q

@login_required(login_url='/admin/login/')
def channel_list(request):
    """List user Telegram channels only"""

    channels = TelegramChannel.objects.filter(
        owner=request.user  # ✅ enforce ownership
    ).select_related('topic').annotate(
        message_count=Count(
            'telegram_deliveries',
            filter=Q(telegram_deliveries__status='sent')
        ),
        total_cost=Sum(
            'telegram_deliveries__cost_charged',
            filter=Q(telegram_deliveries__status='sent')
        )
    ).order_by('-is_active', 'name')

    # Replace None with Decimal 0
    for channel in channels:
        channel.total_cost = channel.total_cost or Decimal('0.00')

    context = {'channels': channels}
    return render(request, 'channels.html', context)


@login_required(login_url='/admin/login/')
def channel_add(request):
    """Add new channel"""

    if request.method == 'POST':
        name = request.POST.get('name')
        channel_id = request.POST.get('channel_id')
        topic_id = request.POST.get('topic')
        price = request.POST.get('price_per_message')
        balance = request.POST.get('balance')

        # ✅ Ensure topic belongs to this user
        topic = get_object_or_404(
            Topic,
            pk=topic_id,
            owner=request.user
        )

        TelegramChannel.objects.create(
            owner=request.user,  # ✅ enforce ownership
            name=name,
            channel_id=channel_id,
            topic=topic,
            price_per_message=Decimal(price),
            balance=Decimal(balance),
            is_active=True,
            last_payment_date=timezone.now()
        )

        messages.success(request, f'Channel "{name}" added!')
        return redirect('dashboard:channel_list')

    # ✅ Only show user's topics
    topics = Topic.objects.filter(owner=request.user)

    context = {'topics': topics, 'action': 'Add'}
    return render(request, 'channel_form.html', context)


@login_required(login_url='/admin/login/')
def channel_edit(request, pk):
    """Edit channel"""

    # ✅ Enforce ownership
    channel = get_object_or_404(
        TelegramChannel,
        pk=pk,
        owner=request.user
    )

    if request.method == 'POST':
        name = request.POST.get('name')
        channel_id = request.POST.get('channel_id')
        topic_id = request.POST.get('topic')
        price = request.POST.get('price_per_message')

        # ✅ Ensure topic belongs to this user
        topic = get_object_or_404(
            Topic,
            pk=topic_id,
            owner=request.user
        )

        channel.name = name
        channel.channel_id = channel_id
        channel.topic = topic
        channel.price_per_message = Decimal(price)
        channel.save()

        messages.success(request, f'Channel "{channel.name}" updated!')
        return redirect('dashboard:channel_list')

    # ✅ Only user's topics
    topics = Topic.objects.filter(owner=request.user)

    context = {
        'channel': channel,
        'topics': topics,
        'action': 'Edit'
    }

    return render(request, 'channel_form.html', context)


@login_required(login_url='/admin/login/')
def channel_toggle(request, pk):
    """Toggle channel active status"""

    if request.method == 'POST':
        channel = get_object_or_404(
            TelegramChannel,
            pk=pk,
            owner=request.user  # ✅ enforce ownership
        )

        channel.is_active = not channel.is_active
        channel.save()

        status = 'activated' if channel.is_active else 'deactivated'
        messages.success(request, f'Channel "{channel.name}" {status}!')

    return redirect('dashboard:channel_list')


from decimal import Decimal, InvalidOperation

@login_required(login_url='/admin/login/')
def channel_add_balance(request, pk):
    """Add balance to channel"""

    if request.method == 'POST':
        # ✅ Enforce ownership
        channel = get_object_or_404(
            TelegramChannel,
            pk=pk,
            owner=request.user
        )

        try:
            amount = Decimal(request.POST.get('amount', '0'))
        except (InvalidOperation, TypeError):
            messages.error(request, "Invalid amount.")
            return redirect('dashboard:channel_list')

        # ✅ Prevent negative or zero deposits
        if amount <= 0:
            messages.error(request, "Amount must be greater than zero.")
            return redirect('dashboard:channel_list')

        channel.balance += amount
        channel.last_payment_date = timezone.now()
        channel.is_active = True
        channel.save()

        messages.success(
            request,
            f'Added ${amount} to "{channel.name}". '
            f'New balance: ${channel.balance}'
        )

    return redirect('dashboard:channel_list')


@login_required(login_url='/admin/login/')
def delivery_list(request):
    """List user deliveries only"""

    # ✅ Enforce ownership through channel
    deliveries = TelegramDelivery.objects.filter(
        telegram_channel__owner=request.user
    ).select_related(
        'telegram_channel',
        'summary',
        'summary__article'
    ).order_by('-sent_date')

    # Filters
    channel_id = request.GET.get('channel')
    status = request.GET.get('status')

    if channel_id:
        # ✅ Ensure channel belongs to user
        deliveries = deliveries.filter(
            telegram_channel_id=channel_id,
            telegram_channel__owner=request.user
        )

    if status:
        deliveries = deliveries.filter(status=status)

    from django.core.paginator import Paginator
    paginator = Paginator(deliveries, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # ✅ Only user's channels in dropdown
    channels = TelegramChannel.objects.filter(owner=request.user)

    context = {
        'page_obj': page_obj,
        'channels': channels,
        'current_channel': channel_id,
        'current_status': status,
    }

    return render(request, 'deliveries.html', context)

@login_required(login_url='/admin/login/')
def statistics(request):
    """Statistics page (tenant isolated)"""

    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    # ✅ Base querysets (VERY IMPORTANT)
    user_articles = Article.objects.filter(owner=request.user)
    user_deliveries = TelegramDelivery.objects.filter(
        telegram_channel__owner=request.user
    )
    user_channels = TelegramChannel.objects.filter(owner=request.user)
    user_topics = Topic.objects.filter(owner=request.user)

    # ================== DATE HANDLING ==================
    try:
        stats = {
            'articles': {
                'today': user_articles.filter(published_date__date=today).count(),
                'week': user_articles.filter(published_date__date__gte=week_ago).count(),
                'month': user_articles.filter(published_date__date__gte=month_ago).count(),
                'total': user_articles.count(),
            },
            'deliveries': {
                'today': user_deliveries.filter(sent_date__date=today, status='sent').count(),
                'week': user_deliveries.filter(sent_date__date__gte=week_ago, status='sent').count(),
                'month': user_deliveries.filter(sent_date__date__gte=month_ago, status='sent').count(),
                'total': user_deliveries.filter(status='sent').count(),
            },
            'revenue': {
                'today': user_deliveries.filter(sent_date__date=today, status='sent')
                    .aggregate(total=Sum('cost_charged'))['total'] or Decimal('0.00'),

                'week': user_deliveries.filter(sent_date__date__gte=week_ago, status='sent')
                    .aggregate(total=Sum('cost_charged'))['total'] or Decimal('0.00'),

                'month': user_deliveries.filter(sent_date__date__gte=month_ago, status='sent')
                    .aggregate(total=Sum('cost_charged'))['total'] or Decimal('0.00'),

                'total': user_deliveries.filter(status='sent')
                    .aggregate(total=Sum('cost_charged'))['total'] or Decimal('0.00'),
            }
        }

    except:
        # Fallback for CharField date fields
        stats = {
            'articles': {
                'today': user_articles.filter(published_date__startswith=str(today)).count(),
                'week': user_articles.count(),
                'month': user_articles.count(),
                'total': user_articles.count(),
            },
            'deliveries': {
                'today': user_deliveries.filter(sent_date__startswith=str(today), status='sent').count(),
                'week': user_deliveries.filter(status='sent').count(),
                'month': user_deliveries.filter(status='sent').count(),
                'total': user_deliveries.filter(status='sent').count(),
            },
            'revenue': {
                'today': user_deliveries.filter(sent_date__startswith=str(today), status='sent')
                    .aggregate(total=Sum('cost_charged'))['total'] or Decimal('0.00'),

                'week': user_deliveries.filter(status='sent')
                    .aggregate(total=Sum('cost_charged'))['total'] or Decimal('0.00'),

                'month': user_deliveries.filter(status='sent')
                    .aggregate(total=Sum('cost_charged'))['total'] or Decimal('0.00'),

                'total': user_deliveries.filter(status='sent')
                    .aggregate(total=Sum('cost_charged'))['total'] or Decimal('0.00'),
            }
        }

    # ================== TOP CHANNELS ==================
    top_channels = user_channels.annotate(
        message_count=Count(
            'telegram_deliveries',
            filter=Q(telegram_deliveries__status='sent')
        )
    ).order_by('-message_count')[:10]

    # ================== TOPICS STATS ==================
    topics_stats = user_topics.annotate(
        article_count=Count(
            'topic_classifications',
            filter=Q(topic_classifications__article__owner=request.user)
        )
    ).order_by('-article_count')

    context = {
        'stats': stats,
        'top_channels': top_channels,
        'topics_stats': topics_stats,
    }

    return render(request, 'statistics.html', context)

@login_required(login_url='/admin/login/')
@require_POST
def run_crawler(request):
    """
    Starts crawler for current user only
    """

    try:
        subprocess.Popen([
            'python',
            'manage.py',
            'crawl_news',
            f'--user_id={request.user.id}'
        ])

        messages.success(request, "Crawler started successfully!")

    except Exception as e:
        messages.error(request, f"Error starting crawler: {e}")

    return redirect('dashboard:home')

@login_required(login_url='/admin/login/')
@require_POST
def run_summarizer(request):
    subprocess.Popen([
        'python',
        'manage.py',
        'summarize',
        f'--user_id={request.user.id}'
    ])
    messages.success(request, "Summarizer started!")
    return redirect('dashboard:home')


@login_required(login_url='/admin/login/')
@require_POST
def run_classifier(request):
    subprocess.Popen([
        'python',
        'manage.py',
        'classify_articles',
        f'--user_id={request.user.id}'
    ])
    messages.success(request, "Classifier started!")
    return redirect('dashboard:home')

@login_required(login_url='/admin/login/')
@require_POST
def run_telegram(request):
    try:
        subprocess.Popen([
            'python',
            'manage.py',
            'send_to_telegram',
            f'--user_id={request.user.id}'
        ])
        messages.success(request, "Telegram sending started!")
    except Exception as e:
        messages.error(request, f"Error starting bot: {e}")

    return redirect('dashboard:home')


def run_command_async(command_name):
    """Run management command in background"""
    try:
        call_command(command_name)
    except Exception as e:
        print(f"Error running {command_name}: {e}")

@login_required(login_url='/admin/login/')
def check_payments(request):
    """Run check_channel_payments command"""
    if request.method == 'POST':
        thread = threading.Thread(target=run_command_async, args=('check_channel_payments',))
        thread.start()
        messages.success(request, 'Payment check started!')
        return redirect('dashboard:home')
    return redirect('dashboard:home')

# ── Add these two views to your views.py ──────────────────────────────────────

@login_required(login_url='/admin/login/')
@require_POST
def summary_edit(request, pk):
    """Edit a summary's text and article title"""
    summary = get_object_or_404(
        Summary,
        pk=pk,
        article__owner=request.user
    )
    new_text = request.POST.get('summary_text', '').strip()
    new_title = request.POST.get('translated_title', '').strip()

    if not new_text:
        messages.error(request, 'Summary text cannot be empty.')
        return redirect('dashboard:summary_list')

    summary.summary_text = new_text
    summary.save()

    if new_title:
        summary.article.title = new_title
        summary.article.save(update_fields=['title'])

    messages.success(request, 'Summary updated successfully!')
    return redirect('dashboard:summary_list')


@login_required(login_url='/admin/login/')
@require_POST
def summary_send_selected(request):
    """Send only the selected summaries to Telegram"""
    summary_ids = request.POST.getlist('summary_ids')

    if not summary_ids:
        messages.error(request, 'No summaries selected.')
        return redirect('dashboard:summary_list')

    # Verify ownership of all selected summaries
    valid_ids = Summary.objects.filter(
        pk__in=summary_ids,
        article__owner=request.user
    ).values_list('pk', flat=True)

    if not valid_ids:
        messages.error(request, 'No valid summaries found.')
        return redirect('dashboard:summary_list')

    # Pass the selected IDs to the management command
    ids_str = ','.join(str(i) for i in valid_ids)
    subprocess.Popen([
        'python',
        'manage.py',
        'send_to_telegram',
        f'--user_id={request.user.id}',
        f'--summary_ids={ids_str}',
    ])

    messages.success(request, f'Sending {len(valid_ids)} summar{"y" if len(valid_ids) == 1 else "ies"} to Telegram!')
    return redirect('dashboard:summary_list')