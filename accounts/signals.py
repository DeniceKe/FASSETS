from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Profile
from .roles import sync_user_role_group

User = get_user_model()

@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
    sync_user_role_group(instance)


@receiver(post_save, sender=Profile)
def sync_profile_role(sender, instance, **kwargs):
    sync_user_role_group(instance.user)
