import time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Profile
from .roles import sync_user_role_group
from .middleware import LAST_ACTIVITY_SESSION_KEY

User = get_user_model()

@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
    sync_user_role_group(instance)


@receiver(post_save, sender=Profile)
def sync_profile_role(sender, instance, **kwargs):
    sync_user_role_group(instance.user)


@receiver(user_logged_in)
def initialize_last_activity(sender, request, user, **kwargs):
    if request is None:
        return

    timeout_seconds = int(getattr(settings, "SESSION_INACTIVITY_TIMEOUT", 300))
    request.session[LAST_ACTIVITY_SESSION_KEY] = int(time.time())
    request.session.set_expiry(timeout_seconds)
