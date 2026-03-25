from django.core.management.base import BaseCommand

from accounts.roles import bootstrap_role_groups

class Command(BaseCommand):
    help = "Create default proposal role groups"

    def handle(self, *args, **options):
        groups = bootstrap_role_groups()
        self.stdout.write(
            self.style.SUCCESS(
                f"Default role groups created/verified: {', '.join(group.name for group in groups.values())}."
            )
        )
