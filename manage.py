#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from pathlib import Path


def bootstrap_local_site_packages():
    """Prefer the project's bundled virtualenv packages when present."""
    site_packages = Path(__file__).resolve().parent / "Lib" / "site-packages"
    if site_packages.is_dir():
        sys.path.insert(0, str(site_packages))


def main():
    """Run administrative tasks."""
    bootstrap_local_site_packages()
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FAssets.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
