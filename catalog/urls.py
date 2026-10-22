from django.urls import path
from . import views

app_name = 'catalog'

urlpatterns = [
    path('', views.home, name='home'),
    path('search/', views.search_locations, name='search'),
    path('l/<slug:slug>/', views.location_detail, name='location_detail'),
]
