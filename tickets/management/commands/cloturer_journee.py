from django.core.management.base import BaseCommand
from django.utils import timezone

from marches.models import Marche
from tickets.services import cloturer_journee


class Command(BaseCommand):
    help = 'Clôture la journée : impayés + pénalité automatique.'

    def add_arguments(self, parser):
        parser.add_argument('--marche-id', type=int)
        parser.add_argument('--date', help='YYYY-MM-DD')

    def handle(self, *args, **options):
        jour = timezone.localdate()
        if options.get('date'):
            from datetime import date
            jour = date.fromisoformat(options['date'])
        qs = Marche.objects.filter(active=True)
        if options.get('marche_id'):
            qs = qs.filter(pk=options['marche_id'])
        for marche in qs:
            try:
                cloture = cloturer_journee(marche, jour=jour)
                self.stdout.write(self.style.SUCCESS(
                    f'{marche} {jour}: {cloture.tickets_impayes} impayé(s), pénalités {cloture.penalites_emises}'
                ))
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f'{marche}: {exc}'))
