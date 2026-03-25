from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Backward-compatible wrapper for bootstrap_roles."

    def handle(self, *args, **options):
        call_command("bootstrap_roles")
