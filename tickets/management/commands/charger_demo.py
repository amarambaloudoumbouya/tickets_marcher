from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import CustomUser, Role
from marches.models import Commune, Marche, PenaliteParametre, Tarif, TypePlace
from recensement.models import Commercant, Place


DEMO_PASSWORD = 'Demo1234!'


class Command(BaseCommand):
    help = 'Charge un marché de démonstration (2 communes, utilisateurs, places).'

    def handle(self, *args, **options):
        kaloum, _ = Commune.objects.get_or_create(code='KAL', defaults={'nom': 'Kaloum'})
        kindia, _ = Commune.objects.get_or_create(code='KIN', defaults={'nom': 'Kindia'})
        madina, _ = Marche.objects.get_or_create(commune=kaloum, nom='Marché Madina', defaults={'adresse': 'Madina'})
        central, _ = Marche.objects.get_or_create(commune=kindia, nom='Marché Central Kindia')
        for marche in (madina, central):
            PenaliteParametre.objects.get_or_create(
                marche=marche,
                defaults={'montant_fixe': 2000, 'pourcentage': 0, 'majoration_par_jour': 0},
            )
            boutique, _ = TypePlace.objects.get_or_create(marche=marche, nom='Boutique')
            table, _ = TypePlace.objects.get_or_create(marche=marche, nom='Table')
            deamb, _ = TypePlace.objects.get_or_create(marche=marche, nom='Déambulant', defaults={'est_deambulant': True})
            jour = timezone.localdate()
            for tp, montant in ((boutique, 5000), (table, 3000), (deamb, 2000)):
                Tarif.objects.get_or_create(type_place=tp, date_debut=jour, defaults={'montant': montant})

        def user(username, role, tel, commune=None, marche=None, **extra):
            obj, created = CustomUser.objects.get_or_create(
                username=username,
                defaults={
                    'telephone': tel,
                    'role': role,
                    'commune': commune,
                    'marche': marche,
                    'first_name': extra.get('first_name', username),
                    'is_staff': role in {Role.ADMIN_GENERAL, Role.ADMIN_COMMUNE},
                    'is_superuser': role == Role.ADMIN_GENERAL,
                },
            )
            if created:
                obj.set_password(DEMO_PASSWORD)
                obj.save()
            return obj

        admin = user('admin', Role.ADMIN_GENERAL, '620000001', first_name='Admin')
        user('admin_madina', Role.ADMIN_COMMUNE, '620000002', commune=kaloum, first_name='Admin Madina')
        user('collecteur', Role.COLLECTEUR, '620000003', commune=kaloum, marche=madina, first_name='Collecteur')
        user('controleur', Role.CONTROLEUR, '620000004', commune=kaloum, marche=madina, first_name='Contrôleur')
        user('regisseur', Role.REGISSEUR, '620000005', commune=kaloum, marche=madina, first_name='Régisseur')
        user('maire', Role.MAIRE, '620000006', commune=kaloum, first_name='Maire')
        fatou_user = user('fatou', Role.COMMERCANT, '622000111', commune=kaloum, marche=madina, first_name='Fatou')

        fatou, _ = Commercant.objects.get_or_create(
            marche=madina, telephone='622000111',
            defaults={'nom': 'Fatou Camara', 'user': fatou_user},
        )
        if not fatou.user_id:
            fatou.user = fatou_user
            fatou.save(update_fields=['user'])
        mamadou, _ = Commercant.objects.get_or_create(
            marche=madina, telephone='622000222', defaults={'nom': 'Mamadou Bah'}
        )
        aissatou, _ = Commercant.objects.get_or_create(
            marche=madina, telephone='622000333', defaults={'nom': 'Aissatou Diallo'}
        )
        boutique = TypePlace.objects.get(marche=madina, nom='Boutique')
        table = TypePlace.objects.get(marche=madina, nom='Table')
        deamb = TypePlace.objects.get(marche=madina, nom='Déambulant')
        Place.objects.get_or_create(marche=madina, code='B12', defaults={'type_place': boutique, 'commercant': fatou})
        Place.objects.get_or_create(marche=madina, code='T04', defaults={'type_place': table, 'commercant': mamadou})
        Place.objects.get_or_create(
            marche=madina, code='D01',
            defaults={'type_place': deamb, 'commercant': aissatou, 'genre': Place.Genre.DEAMBULANT},
        )
        from tickets.services import generer_tickets_du_jour
        n = len(generer_tickets_du_jour(madina))
        self.stdout.write(self.style.SUCCESS(
            'Démo prête. Connexions : admin / collecteur / controleur / regisseur / maire / fatou — mot de passe Demo1234!'
        ))
        self.stdout.write(f'Admin pk={admin.pk}, marché Madina pk={madina.pk}, tickets du jour générés: {n}')
