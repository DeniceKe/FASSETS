from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .forms import AccountProfileForm, SignUpForm


def signup(request):
    if request.user.is_authenticated:
        return redirect("assets:dashboard")

    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Your account has been created. You can now sign in.")
            return redirect("login")
    else:
        form = SignUpForm()

    return render(request, "registration/signup.html", {"form": form})


def csrf_failure(request, reason="", template_name="errors/csrf_failure.html"):
    login_path = reverse("login")
    if request.method == "POST" and request.path == login_path:
        messages.error(
            request,
            "Your sign-in page expired. Please try again with the refreshed login form.",
        )
        response = redirect("login")
        response.delete_cookie(
            settings.CSRF_COOKIE_NAME,
            path=settings.CSRF_COOKIE_PATH,
            domain=settings.CSRF_COOKIE_DOMAIN,
            samesite=settings.CSRF_COOKIE_SAMESITE,
        )
        return response

    return render(request, template_name, {"reason": reason}, status=403)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def logout_view(request):
    if request.user.is_authenticated:
        auth_logout(request)
        messages.success(request, "You have been logged out successfully.")
    return redirect("login")


@login_required
def profile(request):
    profile = request.user.profile

    if request.method == "POST":
        form = AccountProfileForm(request.POST, request.FILES, instance=profile, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile details have been updated.")
            return redirect("profile")
    else:
        form = AccountProfileForm(instance=profile, user=request.user)

    return render(
        request,
        "accounts/profile.html",
        {
            "profile_form": form,
            "profile_user": request.user,
            "profile": profile,
            "show_staff_location_field": "staff_location" in form.fields,
        },
    )
