# dashboard/urls.py
from django.urls import path
from . import views


app_name = 'dashboard'

urlpatterns = [
    # Main Dashboard
    path('', views.dashboard_home, name='home'),


    path('articles/', views.article_list, name='article_list'),
    path('articles/<int:pk>/', views.article_detail, name='article_detail'),
    path('articles/delete/<int:pk>/', views.article_delete, name='article_delete'),
    path('summaries/', views.summary_list, name='summary_list'),
    path('classifications/', views.classification_list, name='classification_list'),


    path('run-crawler/', views.run_crawler, name='run_crawler'),
    path('run-summarizer/', views.run_summarizer, name='run_summarizer'),
    path('run-classifier/', views.run_classifier, name='run_classifier'),
    path('run_telegram/', views.run_telegram, name='run_telegram'),


    path('topics/', views.topic_list, name='topic_list'),
    path('topics/add/', views.topic_add, name='topic_add'),
    path('topics/edit/<int:pk>/', views.topic_edit, name='topic_edit'),
    path('topics/delete/<int:pk>/', views.topic_delete, name='topic_delete'),

    path('channels/', views.channel_list, name='channel_list'),
    path('channels/add/', views.channel_add, name='channel_add'),
    path('channels/edit/<int:pk>/', views.channel_edit, name='channel_edit'),
    path('channels/toggle/<int:pk>/', views.channel_toggle, name='channel_toggle'),
    path('channels/add-balance/<int:pk>/', views.channel_add_balance, name='channel_add_balance'),

    path('deliveries/', views.delivery_list, name='delivery_list'),
    path('run-telegram/', views.run_telegram, name='run_telegram'),
    path('check-payments/', views.check_payments, name='check_payments'),


    path('stats/', views.statistics, name='statistics'),
]
