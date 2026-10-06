from django.core.management.base import BaseCommand
from django.utils import timezone

from marches.models import Marche
from tickets.services import generer_tickets_du_jour


class Command(BaseCommand):
    help = 'Génère les tickets du jour pour les places actives.'

    def add_arguments(self, parser):
        parser.add_argument('--marche-id', type=int)

    def handle(self, *args, **options):
        jour = timezone.localdate()
        qs = Marche.objects.filter(active=True)
        if options.get('marche_id'):
            qs = qs.filter(pk=options['marche_id'])
        total = 0
        for marche in qs:
            crees = generer_tickets_du_jour(marche, jour=jour)
            total += len(crees)
            self.stdout.write(f'{marche}: {len(crees)} ticket(s)')
        self.stdout.write(self.style.SUCCESS(f'Total {total}'))
