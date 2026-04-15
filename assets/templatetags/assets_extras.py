from django import template
from django.utils import timezone

from assets.notifications import build_user_notifications

register = template.Library()


@register.filter
def get_item(mapping, key):
    if mapping is None:
        return None
    return mapping.get(key)


@register.simple_tag
def greeting_for_time(user=None):
    hour = timezone.localtime().hour
    if hour < 12:
        greeting = "Good Morning"
    elif hour < 17:
        greeting = "Good Afternoon"
    else:
        greeting = "Good Evening"

    if user is None:
        return f"{greeting}!"

    display_name = ""
    first_name = getattr(user, "first_name", "") or ""
    if first_name.strip():
        display_name = first_name.strip()
    else:
        display_name = getattr(user, "username", "") or ""

    if display_name:
        return f"{greeting}, {display_name}!"
    return f"{greeting}!"


@register.simple_tag
def dashboard_notifications_for(user):
    notifications = build_user_notifications(user)
    return {
        "notifications": notifications,
        "count": len(notifications),
        "has_items": bool(notifications),
    }
