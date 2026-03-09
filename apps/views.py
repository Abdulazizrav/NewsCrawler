from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.management import call_command
from django.db.models import Count, Sum, Q
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal, InvalidOperation
import threading
import subprocess
from django.views.decorators.http import require_POST

from apps.models import Article, TelegramDelivery, TelegramChannel, Summary, Classification, Topic
from apps.models.user_profile import UserProfile
from apps.permissions import superadmin_required, any_admin_required, is_superadmin


# ══════════════════════════════════════════════════════════
#  SHARED HOME — routes to correct dashboard by role
# ══════════════════════════════════════════════════════════

@login_required(login_url='/login/')
def dashboard_home(request):
    if is_superadmin(request.user):
        return redirect('dashboard:superadmin_home')
    return channel_admin_home(request)


# ══════════════════════════════════════════════════════════
#  CHANNEL ADMIN DASHBOARD
# ══════════════════════════════════════════════════════════

@login_required(login_url='/login/')
def channel_admin_home(request):
    today = timezone.now().date()

    user_articles   = Article.objects.filter(owner=request.user)
    user_channels   = TelegramChannel.objects.filter(owner=request.user)
    user_deliveries = TelegramDelivery.objects.filter(telegram_channel__owner=request.user)

    total_articles    = user_articles.count()
    total_summaries   = user_articles.filter(is_summary=True).count()
    pending_summaries = user_articles.filter(is_summary=False).count()
    active_channels   = user_channels.filter(is_active=True).count()
    total_channels    = user_channels.count()
    total_delivered   = user_deliveries.filter(status='sent').count()

    try:
        articles_today  = user_articles.filter(published_date__date=today).count()
        messages_today  = user_deliveries.filter(sent_date__date=today).count()
        revenue_today   = user_deliveries.filter(sent_date__date=today, status='sent') \
                            .aggregate(total=Sum('cost_charged'))['total'] or Decimal('0.00')
    except Exception:
        articles_today  = user_articles.filter(published_date__startswith=str(today)).count()
        messages_today  = user_deliveries.filter(sent_date__startswith=str(today)).count()
        revenue_today   = Decimal('0.00')

    low_balance_channels = user_channels.filter(balance__lt=10, is_active=True).order_by('balance')[:5]

    recent_articles = user_articles.order_by('-published_date')[:5]
    for article in recent_articles:
        article.has_summary = Summary.objects.filter(article=article).exists()

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


# ══════════════════════════════════════════════════════════
#  SUPERADMIN DASHBOARD
# ══════════════════════════════════════════════════════════

@superadmin_required
def superadmin_home(request):
    """Superadmin overview: all users, revenue, stats."""
    today    = timezone.now().date()
    week_ago = today - timedelta(days=7)

    all_users     = UserProfile.objects.select_related('user', 'created_by').order_by('-created_at')
    channel_admins = all_users.filter(role='channel_admin')

    all_deliveries = TelegramDelivery.objects.filter(status='sent')
    all_channels   = TelegramChannel.objects.all()
    all_articles   = Article.objects.all()

    try:
        total_revenue       = all_deliveries.aggregate(t=Sum('cost_charged'))['t'] or Decimal('0.00')
        revenue_today       = all_deliveries.filter(sent_date__date=today).aggregate(t=Sum('cost_charged'))['t'] or Decimal('0.00')
        revenue_week        = all_deliveries.filter(sent_date__date__gte=week_ago).aggregate(t=Sum('cost_charged'))['t'] or Decimal('0.00')
        messages_today      = all_deliveries.filter(sent_date__date=today).count()
    except Exception:
        total_revenue = revenue_today = revenue_week = Decimal('0.00')
        messages_today = 0

    # Per-user billing summary
    user_billing = []
    for profile in channel_admins:
        u = profile.user
        deliveries = TelegramDelivery.objects.filter(telegram_channel__owner=u, status='sent')
        spent = deliveries.aggregate(t=Sum('cost_charged'))['t'] or Decimal('0.00')
        channels = TelegramChannel.objects.filter(owner=u)
        total_balance = channels.aggregate(t=Sum('balance'))['t'] or Decimal('0.00')
        user_billing.append({
            'profile':       profile,
            'spent':         spent,
            'total_balance': total_balance,
            'channels':      channels.count(),
            'articles':      Article.objects.filter(owner=u).count(),
            'messages_sent': deliveries.count(),
        })

    context = {
        'all_users':       all_users,
        'channel_admins':  channel_admins,
        'total_revenue':   total_revenue,
        'revenue_today':   revenue_today,
        'revenue_week':    revenue_week,
        'messages_today':  messages_today,
        'total_channels':  all_channels.count(),
        'total_articles':  all_articles.count(),
        'user_billing':    user_billing,
    }
    return render(request, 'superadmin/home.html', context)


@superadmin_required
def superadmin_users(request):
    """List and manage channel admins."""
    users = UserProfile.objects.select_related('user', 'created_by').order_by('-created_at')
    context = {'users': users}
    return render(request, 'superadmin/users.html', context)


@superadmin_required
@require_POST
def superadmin_user_create(request):
    """Create a new channel admin account."""
    username  = request.POST.get('username', '').strip()
    password  = request.POST.get('password', '').strip()
    email     = request.POST.get('email', '').strip()
    first_name = request.POST.get('first_name', '').strip()

    if not username or not password:
        messages.error(request, 'Username and password are required.')
        return redirect('dashboard:superadmin_users')

    if User.objects.filter(username=username).exists():
        messages.error(request, f'Username "{username}" already exists.')
        return redirect('dashboard:superadmin_users')

    user = User.objects.create_user(
        username=username,
        password=password,
        email=email,
        first_name=first_name,
    )
    UserProfile.objects.create(
        user=user,
        role='channel_admin',
        created_by=request.user,
        is_active=True,
    )
    messages.success(request, f'Channel admin "{username}" created successfully!')
    return redirect('dashboard:superadmin_users')


@superadmin_required
@require_POST
def superadmin_user_toggle(request, pk):
    """Activate / deactivate a channel admin."""
    profile = get_object_or_404(UserProfile, pk=pk)
    profile.is_active = not profile.is_active
    profile.save()
    profile.user.is_active = profile.is_active
    profile.user.save()
    status = 'activated' if profile.is_active else 'deactivated'
    messages.success(request, f'User "{profile.user.username}" {status}.')
    return redirect('dashboard:superadmin_users')


@superadmin_required
@require_POST
def superadmin_user_delete(request, pk):
    """Delete a channel admin and all their data."""
    profile = get_object_or_404(UserProfile, pk=pk)
    username = profile.user.username
    profile.user.delete()   # cascades to profile, articles, channels, etc.
    messages.success(request, f'User "{username}" and all their data deleted.')
    return redirect('dashboard:superadmin_users')


@superadmin_required
def superadmin_user_detail(request, pk):
    """View full stats for a specific channel admin."""
    profile  = get_object_or_404(UserProfile, pk=pk)
    u        = profile.user
    today    = timezone.now().date()
    week_ago = today - timedelta(days=7)

    channels   = TelegramChannel.objects.filter(owner=u).select_related('topic')
    deliveries = TelegramDelivery.objects.filter(telegram_channel__owner=u)
    articles   = Article.objects.filter(owner=u)

    try:
        total_spent    = deliveries.filter(status='sent').aggregate(t=Sum('cost_charged'))['t'] or Decimal('0.00')
        spent_today    = deliveries.filter(status='sent', sent_date__date=today).aggregate(t=Sum('cost_charged'))['t'] or Decimal('0.00')
        spent_week     = deliveries.filter(status='sent', sent_date__date__gte=week_ago).aggregate(t=Sum('cost_charged'))['t'] or Decimal('0.00')
        total_balance  = channels.aggregate(t=Sum('balance'))['t'] or Decimal('0.00')
    except Exception:
        total_spent = spent_today = spent_week = total_balance = Decimal('0.00')

    context = {
        'profile':      profile,
        'channels':     channels,
        'total_spent':  total_spent,
        'spent_today':  spent_today,
        'spent_week':   spent_week,
        'total_balance': total_balance,
        'articles_count': articles.count(),
        'summaries_count': Summary.objects.filter(article__owner=u).count(),
        'messages_sent': deliveries.filter(status='sent').count(),
        'messages_failed': deliveries.filter(status='failed').count(),
    }
    return render(request, 'superadmin/user_detail.html', context)


@superadmin_required
def superadmin_billing(request):
    """Full billing page across all users."""
    today    = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    profiles = UserProfile.objects.filter(role='channel_admin').select_related('user')

    billing_data = []
    for profile in profiles:
        u = profile.user
        d = TelegramDelivery.objects.filter(telegram_channel__owner=u, status='sent')
        try:
            billing_data.append({
                'profile':     profile,
                'total':       d.aggregate(t=Sum('cost_charged'))['t'] or Decimal('0.00'),
                'today':       d.filter(sent_date__date=today).aggregate(t=Sum('cost_charged'))['t'] or Decimal('0.00'),
                'week':        d.filter(sent_date__date__gte=week_ago).aggregate(t=Sum('cost_charged'))['t'] or Decimal('0.00'),
                'month':       d.filter(sent_date__date__gte=month_ago).aggregate(t=Sum('cost_charged'))['t'] or Decimal('0.00'),
                'msg_count':   d.count(),
                'balance':     TelegramChannel.objects.filter(owner=u).aggregate(t=Sum('balance'))['t'] or Decimal('0.00'),
            })
        except Exception:
            billing_data.append({
                'profile': profile,
                'total': Decimal('0.00'), 'today': Decimal('0.00'),
                'week': Decimal('0.00'), 'month': Decimal('0.00'),
                'msg_count': 0, 'balance': Decimal('0.00'),
            })

    grand_total = sum(b['total'] for b in billing_data)
    context = {'billing_data': billing_data, 'grand_total': grand_total}
    return render(request, 'superadmin/billing.html', context)


@superadmin_required
def superadmin_statistics(request):
    """Platform-wide statistics."""
    today    = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    all_d = TelegramDelivery.objects.filter(status='sent')

    try:
        stats = {
            'revenue': {
                'today': all_d.filter(sent_date__date=today).aggregate(t=Sum('cost_charged'))['t'] or Decimal('0.00'),
                'week':  all_d.filter(sent_date__date__gte=week_ago).aggregate(t=Sum('cost_charged'))['t'] or Decimal('0.00'),
                'month': all_d.filter(sent_date__date__gte=month_ago).aggregate(t=Sum('cost_charged'))['t'] or Decimal('0.00'),
                'total': all_d.aggregate(t=Sum('cost_charged'))['t'] or Decimal('0.00'),
            },
            'messages': {
                'today': all_d.filter(sent_date__date=today).count(),
                'week':  all_d.filter(sent_date__date__gte=week_ago).count(),
                'month': all_d.filter(sent_date__date__gte=month_ago).count(),
                'total': all_d.count(),
            },
        }
    except Exception:
        stats = {
            'revenue':  {'today': 0, 'week': 0, 'month': 0, 'total': 0},
            'messages': {'today': 0, 'week': 0, 'month': 0, 'total': 0},
        }

    stats['users']    = UserProfile.objects.filter(role='channel_admin').count()
    stats['channels'] = TelegramChannel.objects.count()
    stats['articles'] = Article.objects.count()

    top_users = []
    for profile in UserProfile.objects.filter(role='channel_admin').select_related('user'):
        d = TelegramDelivery.objects.filter(telegram_channel__owner=profile.user, status='sent')
        spent = d.aggregate(t=Sum('cost_charged'))['t'] or Decimal('0.00')
        top_users.append({'profile': profile, 'spent': spent, 'count': d.count()})
    top_users.sort(key=lambda x: x['spent'], reverse=True)

    context = {'stats': stats, 'top_users': top_users[:10]}
    return render(request, 'superadmin/statistics.html', context)


# ══════════════════════════════════════════════════════════
#  CHANNEL ADMIN VIEWS (unchanged logic, kept clean)
# ══════════════════════════════════════════════════════════

@login_required(login_url='/login/')
def article_list(request):
    articles = Article.objects.filter(owner=request.user).order_by('-published_date')
    source = request.GET.get('source')
    has_summary = request.GET.get('has_summary')
    search = request.GET.get('search')

    if source:
        articles = articles.filter(source__icontains=source)

    user_summaries = Summary.objects.filter(article__owner=request.user).values_list('article_id', flat=True)

    if has_summary == 'yes':
        articles = articles.filter(id__in=user_summaries)
    elif has_summary == 'no':
        articles = articles.exclude(id__in=user_summaries)

    if search:
        articles = articles.filter(Q(title__icontains=search) | Q(content__icontains=search))

    article_ids_with_summaries = set(user_summaries)
    for article in articles:
        article.has_summary = article.id in article_ids_with_summaries

    from django.core.paginator import Paginator
    paginator = Paginator(articles, 50)
    page_obj = paginator.get_page(request.GET.get('page'))
    sources = Article.objects.filter(owner=request.user).values_list('source', flat=True).distinct()

    context = {
        'page_obj': page_obj,
        'sources': sources,
        'current_source': source,
        'current_has_summary': has_summary,
        'current_search': search,
    }
    return render(request, 'articles.html', context)


@login_required(login_url='/login/')
def article_detail(request, pk):
    article = get_object_or_404(Article, pk=pk, owner=request.user)
    summary = Summary.objects.filter(article=article).first()
    classifications = Classification.objects.filter(article=article).select_related('topic')
    context = {'article': article, 'summary': summary, 'classifications': classifications}
    return render(request, 'article_detail.html', context)


@login_required(login_url='/login/')
def article_delete(request, pk):
    if request.method == 'POST':
        article = get_object_or_404(Article, pk=pk, owner=request.user)
        article.delete()
        messages.success(request, 'Article deleted successfully!')
        return redirect('dashboard:article_list')
    return redirect('dashboard:article_list')


@login_required(login_url='/login/')
def summary_list(request):
    summaries = Summary.objects.filter(article__owner=request.user).select_related('article').order_by('-created_date')
    from django.core.paginator import Paginator
    page_obj = Paginator(summaries, 30).get_page(request.GET.get('page'))
    user_channels = TelegramChannel.objects.filter(owner=request.user, is_active=True).select_related('topic').order_by('name')
    return render(request, 'summaries.html', {'page_obj': page_obj, 'user_channels': user_channels})


@login_required(login_url='/login/')
@require_POST
def summary_edit(request, pk):
    summary = get_object_or_404(Summary, pk=pk, article__owner=request.user)
    new_text  = request.POST.get('summary_text', '').strip()
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


@login_required(login_url='/login/')
@require_POST
def summary_send_selected(request):
    summary_ids = request.POST.getlist('summary_ids')
    channel_ids = request.POST.getlist('channel_ids')

    if not summary_ids:
        messages.error(request, 'No summaries selected.')
        return redirect('dashboard:summary_list')
    if not channel_ids:
        messages.error(request, 'No channels selected.')
        return redirect('dashboard:summary_list')

    valid_summary_ids = list(Summary.objects.filter(pk__in=summary_ids, article__owner=request.user).values_list('pk', flat=True))
    valid_channel_ids = list(TelegramChannel.objects.filter(pk__in=channel_ids, owner=request.user, is_active=True).values_list('pk', flat=True))

    if not valid_summary_ids or not valid_channel_ids:
        messages.error(request, 'No valid summaries or channels found.')
        return redirect('dashboard:summary_list')

    subprocess.Popen([
        'python', 'manage.py', 'send_to_telegram',
        f'--user_id={request.user.id}',
        f'--summary_ids={",".join(str(i) for i in valid_summary_ids)}',
        f'--channel_ids={",".join(str(i) for i in valid_channel_ids)}',
    ])
    messages.success(request, f'Sending {len(valid_summary_ids)} summaries to {len(valid_channel_ids)} channels!')
    return redirect('dashboard:summary_list')


@login_required(login_url='/login/')
def classification_list(request):
    classifications = Classification.objects.filter(article__owner=request.user).select_related('article', 'topic').order_by('-id')
    topic_filter = request.GET.get('topic')
    if topic_filter:
        classifications = classifications.filter(topic_id=topic_filter, topic__owner=request.user)
    from django.core.paginator import Paginator
    page_obj = Paginator(classifications, 30).get_page(request.GET.get('page'))
    topics = Topic.objects.filter(owner=request.user)
    return render(request, 'classifications.html', {'page_obj': page_obj, 'topics': topics, 'current_topic': topic_filter})


@login_required(login_url='/login/')
def topic_list(request):
    topics = Topic.objects.filter(owner=request.user)
    for topic in topics:
        topic.article_count = Classification.objects.filter(topic=topic, article__owner=request.user).count()
        topic.channel_count = TelegramChannel.objects.filter(topic=topic, owner=request.user).count()
        topic.keyword_list = [k.strip() for k in topic.keywords.split(',')] if topic.keywords else []
    return render(request, 'topics.html', {'topics': topics})


@login_required(login_url='/login/')
def topic_add(request):
    if request.method == 'POST':
        Topic.objects.create(owner=request.user, name=request.POST.get('name'), keywords=request.POST.get('keywords'))
        messages.success(request, f'Topic "{request.POST.get("name")}" added!')
        return redirect('dashboard:topic_list')
    return render(request, 'topic_form.html', {'action': 'Add'})


@login_required(login_url='/login/')
def topic_edit(request, pk):
    topic = get_object_or_404(Topic, pk=pk, owner=request.user)
    if request.method == 'POST':
        topic.name = request.POST.get('name')
        topic.keywords = request.POST.get('keywords')
        topic.save()
        messages.success(request, f'Topic "{topic.name}" updated!')
        return redirect('dashboard:topic_list')
    return render(request, 'topic_form.html', {'topic': topic, 'action': 'Edit'})


@login_required(login_url='/login/')
def topic_delete(request, pk):
    if request.method == 'POST':
        topic = get_object_or_404(Topic, pk=pk, owner=request.user)
        name = topic.name
        topic.delete()
        messages.success(request, f'Topic "{name}" deleted!')
    return redirect('dashboard:topic_list')


@login_required(login_url='/login/')
def channel_list(request):
    channels = TelegramChannel.objects.filter(owner=request.user).select_related('topic').annotate(
        message_count=Count('telegram_deliveries', filter=Q(telegram_deliveries__status='sent')),
        total_cost=Sum('telegram_deliveries__cost_charged', filter=Q(telegram_deliveries__status='sent'))
    ).order_by('-is_active', 'name')
    for channel in channels:
        channel.total_cost = channel.total_cost or Decimal('0.00')
    return render(request, 'channels.html', {'channels': channels})


@login_required(login_url='/login/')
def channel_add(request):
    if request.method == 'POST':
        topic = get_object_or_404(Topic, pk=request.POST.get('topic'), owner=request.user)
        TelegramChannel.objects.create(
            owner=request.user,
            name=request.POST.get('name'),
            channel_id=request.POST.get('channel_id'),
            topic=topic,
            price_per_message=Decimal(request.POST.get('price_per_message')),
            balance=Decimal(request.POST.get('balance')),
            is_active=True,
            last_payment_date=timezone.now()
        )
        messages.success(request, f'Channel "{request.POST.get("name")}" added!')
        return redirect('dashboard:channel_list')
    topics = Topic.objects.filter(owner=request.user)
    return render(request, 'channel_form.html', {'topics': topics, 'action': 'Add'})


@login_required(login_url='/login/')
def channel_edit(request, pk):
    channel = get_object_or_404(TelegramChannel, pk=pk, owner=request.user)
    if request.method == 'POST':
        topic = get_object_or_404(Topic, pk=request.POST.get('topic'), owner=request.user)
        channel.name = request.POST.get('name')
        channel.channel_id = request.POST.get('channel_id')
        channel.topic = topic
        channel.price_per_message = Decimal(request.POST.get('price_per_message'))
        channel.save()
        messages.success(request, f'Channel "{channel.name}" updated!')
        return redirect('dashboard:channel_list')
    topics = Topic.objects.filter(owner=request.user)
    return render(request, 'channel_form.html', {'channel': channel, 'topics': topics, 'action': 'Edit'})


@login_required(login_url='/login/')
def channel_toggle(request, pk):
    if request.method == 'POST':
        channel = get_object_or_404(TelegramChannel, pk=pk, owner=request.user)
        channel.is_active = not channel.is_active
        channel.save()
        messages.success(request, f'Channel "{channel.name}" {"activated" if channel.is_active else "deactivated"}!')
    return redirect('dashboard:channel_list')


@login_required(login_url='/login/')
def channel_add_balance(request, pk):
    if request.method == 'POST':
        channel = get_object_or_404(TelegramChannel, pk=pk, owner=request.user)
        try:
            amount = Decimal(request.POST.get('amount', '0'))
        except (InvalidOperation, TypeError):
            messages.error(request, 'Invalid amount.')
            return redirect('dashboard:channel_list')
        if amount <= 0:
            messages.error(request, 'Amount must be greater than zero.')
            return redirect('dashboard:channel_list')
        channel.balance += amount
        channel.last_payment_date = timezone.now()
        channel.is_active = True
        channel.save()
        messages.success(request, f'Added ${amount} to "{channel.name}". New balance: ${channel.balance}')
    return redirect('dashboard:channel_list')


@login_required(login_url='/login/')
def delivery_list(request):
    deliveries = TelegramDelivery.objects.filter(telegram_channel__owner=request.user) \
        .select_related('telegram_channel', 'summary', 'summary__article').order_by('-sent_date')
    channel_id = request.GET.get('channel')
    status = request.GET.get('status')
    if channel_id:
        deliveries = deliveries.filter(telegram_channel_id=channel_id, telegram_channel__owner=request.user)
    if status:
        deliveries = deliveries.filter(status=status)
    from django.core.paginator import Paginator
    page_obj = Paginator(deliveries, 50).get_page(request.GET.get('page'))
    channels = TelegramChannel.objects.filter(owner=request.user)
    return render(request, 'deliveries.html', {'page_obj': page_obj, 'channels': channels, 'current_channel': channel_id, 'current_status': status})


@login_required(login_url='/login/')
def statistics(request):
    today    = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    user_articles   = Article.objects.filter(owner=request.user)
    user_deliveries = TelegramDelivery.objects.filter(telegram_channel__owner=request.user)
    user_channels   = TelegramChannel.objects.filter(owner=request.user)
    user_topics     = Topic.objects.filter(owner=request.user)

    try:
        stats = {
            'articles':   {'today': user_articles.filter(published_date__date=today).count(), 'week': user_articles.filter(published_date__date__gte=week_ago).count(), 'month': user_articles.filter(published_date__date__gte=month_ago).count(), 'total': user_articles.count()},
            'deliveries': {'today': user_deliveries.filter(sent_date__date=today, status='sent').count(), 'week': user_deliveries.filter(sent_date__date__gte=week_ago, status='sent').count(), 'month': user_deliveries.filter(sent_date__date__gte=month_ago, status='sent').count(), 'total': user_deliveries.filter(status='sent').count()},
            'revenue':    {'today': user_deliveries.filter(sent_date__date=today, status='sent').aggregate(t=Sum('cost_charged'))['t'] or Decimal('0.00'), 'week': user_deliveries.filter(sent_date__date__gte=week_ago, status='sent').aggregate(t=Sum('cost_charged'))['t'] or Decimal('0.00'), 'month': user_deliveries.filter(sent_date__date__gte=month_ago, status='sent').aggregate(t=Sum('cost_charged'))['t'] or Decimal('0.00'), 'total': user_deliveries.filter(status='sent').aggregate(t=Sum('cost_charged'))['t'] or Decimal('0.00')},
        }
    except Exception:
        stats = {'articles': {'today': 0, 'week': 0, 'month': 0, 'total': user_articles.count()}, 'deliveries': {'today': 0, 'week': 0, 'month': 0, 'total': 0}, 'revenue': {'today': Decimal('0.00'), 'week': Decimal('0.00'), 'month': Decimal('0.00'), 'total': Decimal('0.00')}}

    top_channels = user_channels.annotate(message_count=Count('telegram_deliveries', filter=Q(telegram_deliveries__status='sent'))).order_by('-message_count')[:10]
    topics_stats = user_topics.annotate(article_count=Count('topic_classifications', filter=Q(topic_classifications__article__owner=request.user))).order_by('-article_count')

    return render(request, 'statistics.html', {'stats': stats, 'top_channels': top_channels, 'topics_stats': topics_stats})


# ── Management command triggers ──────────────────────────

@login_required(login_url='/login/')
@require_POST
def run_crawler(request):
    try:
        subprocess.Popen(['python', 'manage.py', 'crawl_news', f'--user_id={request.user.id}'])
        messages.success(request, 'Crawler started!')
    except Exception as e:
        messages.error(request, f'Error: {e}')
    return redirect('dashboard:home')


@login_required(login_url='/login/')
@require_POST
def run_summarizer(request):
    subprocess.Popen(['python', 'manage.py', 'summarize', f'--user_id={request.user.id}'])
    messages.success(request, 'Summarizer started!')
    return redirect('dashboard:home')


@login_required(login_url='/login/')
@require_POST
def run_classifier(request):
    subprocess.Popen(['python', 'manage.py', 'classify_articles', f'--user_id={request.user.id}'])
    messages.success(request, 'Classifier started!')
    return redirect('dashboard:home')


@login_required(login_url='/login/')
@require_POST
def run_telegram(request):
    try:
        subprocess.Popen(['python', 'manage.py', 'send_to_telegram', f'--user_id={request.user.id}'])
        messages.success(request, 'Telegram sending started!')
    except Exception as e:
        messages.error(request, f'Error: {e}')
    return redirect('dashboard:home')


@login_required(login_url='/login/')
def check_payments(request):
    if request.method == 'POST':
        threading.Thread(target=lambda: call_command('check_channel_payments')).start()
        messages.success(request, 'Payment check started!')
    return redirect('dashboard:home')