from django.urls import include, path

from .views import logout_view, profile, signup

urlpatterns = [
    path("signup/", signup, name="signup"),
    path("profile/", profile, name="profile"),
    path("logout/", logout_view, name="logout"),
    path("", include("django.contrib.auth.urls")),
]
