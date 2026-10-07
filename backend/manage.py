#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    # Les tests doivent rester DÉTERMINISTES : on force DJANGO_TESTING=true
    # pour que (a) settings.py bascule sur SQLite en mémoire et (b) l'agent IA
    # utilise le moteur de règles au lieu d'appeler DeepSeek (non déterministe),
    # même si la clé DEEPSEEK_API_KEY est présente dans backend/.env.
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        os.environ.setdefault("DJANGO_TESTING", "true")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
