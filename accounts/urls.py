from django.urls import include, path

from .views import signup

urlpatterns = [
    path("signup/", signup, name="signup"),
    path("", include("django.contrib.auth.urls")),
]
