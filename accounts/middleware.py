import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.views import redirect_to_login
from django.http import JsonResponse


LAST_ACTIVITY_SESSION_KEY = "last_activity_at"


class InactiveSessionLogoutMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        timeout_seconds = int(getattr(settings, "SESSION_INACTIVITY_TIMEOUT", 300))
        timeout_minutes = max(1, timeout_seconds // 60)
        timeout_message = (
            f"Your session expired after {timeout_minutes} minutes of inactivity. Please sign in again."
        )

        if getattr(request, "user", None) and request.user.is_authenticated:
            current_timestamp = int(time.time())
            last_activity_timestamp = request.session.get(LAST_ACTIVITY_SESSION_KEY)

            if last_activity_timestamp is not None:
                try:
                    last_activity_timestamp = int(last_activity_timestamp)
                except (TypeError, ValueError):
                    last_activity_timestamp = None

            if (
                last_activity_timestamp is not None
                and current_timestamp - last_activity_timestamp >= timeout_seconds
            ):
                auth_logout(request)

                if request.path.startswith("/api/"):
                    return JsonResponse(
                        {
                            "detail": timeout_message,
                        },
                        status=401,
                    )

                messages.warning(request, timeout_message)
                return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)

        response = self.get_response(request)

        if getattr(request, "user", None) and request.user.is_authenticated:
            request.session[LAST_ACTIVITY_SESSION_KEY] = int(time.time())
            request.session.set_expiry(timeout_seconds)

        return response
