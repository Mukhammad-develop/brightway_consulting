"""
URL configuration for public website.
"""

from django.urls import path
from . import views

app_name = 'public'

urlpatterns = [
    path('', views.index, name='index'),
    path('services/', views.services, name='services'),
    path('contact/', views.contact, name='contact'),
    path('set-language/<str:lang>/', views.set_language, name='set_language'),
]
