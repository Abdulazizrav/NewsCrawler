from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.dashboard_home, name='home'),

    # Superadmin
    path('superadmin/',                          views.superadmin_home,          name='superadmin_home'),
    path('superadmin/users/',                    views.superadmin_users,         name='superadmin_users'),
    path('superadmin/users/create/',             views.superadmin_user_create,   name='superadmin_user_create'),
    path('superadmin/users/<int:pk>/toggle/',    views.superadmin_user_toggle,   name='superadmin_user_toggle'),
    path('superadmin/users/<int:pk>/delete/',    views.superadmin_user_delete,   name='superadmin_user_delete'),
    path('superadmin/users/<int:pk>/',           views.superadmin_user_detail,   name='superadmin_user_detail'),
    path('superadmin/billing/',                  views.superadmin_billing,       name='superadmin_billing'),
    path('superadmin/statistics/',               views.superadmin_statistics,    name='superadmin_statistics'),

    # Articles
    path('articles/',                 views.article_list,   name='article_list'),
    path('articles/<int:pk>/',        views.article_detail, name='article_detail'),
    path('articles/delete/<int:pk>/', views.article_delete, name='article_delete'),

    # Summaries
    path('summaries/',               views.summary_list,          name='summary_list'),
    path('summaries/<int:pk>/edit/', views.summary_edit,          name='summary_edit'),
    path('summaries/send-selected/', views.summary_send_selected, name='summary_send_selected'),

    # Classifications
    path('classifications/', views.classification_list, name='classification_list'),

    # Topics
    path('topics/',                 views.topic_list,   name='topic_list'),
    path('topics/select/',          views.topic_select, name='topic_select'),
    path('topics/add/',             views.topic_add,    name='topic_add'),
    path('topics/edit/<int:pk>/',   views.topic_edit,   name='topic_edit'),
    path('topics/delete/<int:pk>/', views.topic_delete, name='topic_delete'),

    # Channels
    path('channels/',                      views.channel_list,        name='channel_list'),
    path('channels/add/',                  views.channel_add,         name='channel_add'),
    path('channels/edit/<int:pk>/',        views.channel_edit,        name='channel_edit'),
    path('channels/toggle/<int:pk>/',      views.channel_toggle,      name='channel_toggle'),
    path('channels/add-balance/<int:pk>/', views.channel_add_balance, name='channel_add_balance'),

    # Deliveries
    path('deliveries/', views.delivery_list, name='delivery_list'),

    # Commands
    path('run-crawler/',    views.run_crawler,    name='run_crawler'),
    path('run-summarizer/', views.run_summarizer, name='run_summarizer'),
    path('run-classifier/', views.run_classifier, name='run_classifier'),
    path('run-telegram/',   views.run_telegram,   name='run_telegram'),
    path('check-payments/', views.check_payments, name='check_payments'),

    # Stats
    path('stats/', views.statistics, name='statistics'),
]