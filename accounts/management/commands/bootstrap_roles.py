from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group

GROUPS = [
    "system_admin",
    "lecturer_staff",
    "technician",
    "chair_department",
    "dean",
    "auditor",
]

class Command(BaseCommand):
    help = "Create default role groups"

    def handle(self, *args, **options):
        for name in GROUPS:
            Group.objects.get_or_create(name=name)
        self.stdout.write(self.style.SUCCESS("Default role groups created/verified."))