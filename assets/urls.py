from django.urls import path
from . import views

app_name = "assets"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("assets/", views.asset_list, name="asset_list"),
]