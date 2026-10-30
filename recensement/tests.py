from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role
from marches.models import Commune, Marche, Tarif, TypePlace
from recensement.models import Commercant, Place
from tickets.models import Ticket

User = get_user_model()


class RecensementUniqueTests(TestCase):
    def setUp(self):
        commune = Commune.objects.create(nom='Kaloum', code='KAL')
        self.marche = Marche.objects.create(commune=commune, nom='Madina')
        self.boutique = TypePlace.objects.create(marche=self.marche, nom='Boutique')
        Tarif.objects.create(type_place=self.boutique, montant=5000, date_debut=timezone.localdate())
        self.collecteur = User.objects.create_user(
            username='col', password='x', telephone='62001', role=Role.COLLECTEUR,
            commune=commune, marche=self.marche,
        )

    def test_le_recensement_cree_le_commercant_la_place_et_le_ticket(self):
        self.client.force_login(self.collecteur)
        response = self.client.post(reverse('recensement:commercants'), {
            'nom': 'Awa Diallo',
            'telephone': '622000999',
            'type_place': self.boutique.pk,
            'code': 'B20',
            'actif': 'on',
        })
        self.assertEqual(response.status_code, 302)
        commercant = Commercant.objects.get(telephone='622000999')
        place = Place.objects.get(commercant=commercant)
        self.assertEqual(place.code, 'B20')
        self.assertEqual(place.type_place, self.boutique)
        self.assertEqual(place.marche, self.marche)
        self.assertTrue(Ticket.objects.filter(place=place, commercant=commercant).exists())

    def test_lancien_formulaire_de_place_renvoie_au_recensement(self):
        self.client.force_login(self.collecteur)
        response = self.client.get(reverse('recensement:place_create'))
        self.assertRedirects(response, reverse('recensement:commercants'))
        page = self.client.get(reverse('recensement:places'))
        self.assertNotContains(page, 'Nouvelle place')
        self.assertContains(page, 'recensement du commerçant')


class ModificationCommercantTests(TestCase):
    def setUp(self):
        self.kaloum = Commune.objects.create(nom='Kaloum', code='KAL')
        self.kindia = Commune.objects.create(nom='Kindia', code='KIN')
        self.marche = Marche.objects.create(commune=self.kaloum, nom='Madina')
        self.autre = Marche.objects.create(commune=self.kindia, nom='Central')
        self.commercant = Commercant.objects.create(marche=self.marche, nom='Fatou', telephone='622111')
        self.exterieur = Commercant.objects.create(marche=self.autre, nom='Mamadou', telephone='622222')
        self.general = User.objects.create_user(
            username='general', password='x', telephone='620000001', role=Role.ADMIN_GENERAL,
        )
        self.admin_commune = User.objects.create_user(
            username='admin_commune', password='x', telephone='620000002',
            role=Role.ADMIN_COMMUNE, commune=self.kaloum,
        )
        self.admin_marche = User.objects.create_user(
            username='admin_marche', password='x', telephone='620000003',
            role=Role.ADMIN_MARCHE, commune=self.kaloum, marche=self.marche,
        )
        self.collecteur = User.objects.create_user(
            username='col', password='x', telephone='620000004', role=Role.COLLECTEUR,
            commune=self.kaloum, marche=self.marche,
        )

    def test_admin_general_modifie_le_commercant(self):
        self.client.force_login(self.general)
        url = reverse('recensement:commercant_update', args=[self.commercant.pk])
        page = self.client.get(url)
        self.assertContains(page, 'Modifier le commerçant')
        response = self.client.post(url, {
            'nom': 'Fatou Camara',
            'telephone': '622333',
        })
        self.assertRedirects(response, reverse('recensement:commercants'))
        self.commercant.refresh_from_db()
        self.assertEqual(self.commercant.nom, 'Fatou Camara')
        self.assertEqual(self.commercant.telephone, '622333')
        self.assertFalse(self.commercant.actif)
        self.assertEqual(Place.objects.filter(commercant=self.commercant).count(), 0)
        liste = self.client.get(reverse('recensement:commercants'))
        self.assertContains(liste, url)

    def test_admin_commune_modifie_un_commercant_de_sa_commune(self):
        self.client.force_login(self.admin_commune)
        response = self.client.post(reverse('recensement:commercant_update', args=[self.commercant.pk]), {
            'nom': 'Fatou Diallo',
            'telephone': '622111',
            'actif': 'on',
        })
        self.assertRedirects(response, reverse('recensement:commercants'))
        self.commercant.refresh_from_db()
        self.assertEqual(self.commercant.nom, 'Fatou Diallo')
        self.assertTrue(self.commercant.actif)

    def test_admin_commune_ne_modifie_pas_une_autre_commune(self):
        self.client.force_login(self.admin_commune)
        response = self.client.get(reverse('recensement:commercant_update', args=[self.exterieur.pk]))
        self.assertEqual(response.status_code, 404)

    def test_les_autres_roles_ne_peuvent_pas_modifier(self):
        for user in (self.admin_marche, self.collecteur):
            self.client.force_login(user)
            response = self.client.get(reverse('recensement:commercant_update', args=[self.commercant.pk]))
            self.assertEqual(response.status_code, 403)
            liste = self.client.get(reverse('recensement:commercants'))
            self.assertNotContains(
                liste,
                reverse('recensement:commercant_update', args=[self.commercant.pk]),
            )

    def test_le_telephone_reste_unique_sur_le_marche(self):
        Commercant.objects.create(marche=self.marche, nom='Awa', telephone='622999')
        self.client.force_login(self.general)
        response = self.client.post(reverse('recensement:commercant_update', args=[self.commercant.pk]), {
            'nom': 'Fatou',
            'telephone': '622999',
            'actif': 'on',
        })
        self.assertEqual(response.status_code, 200)
        self.commercant.refresh_from_db()
        self.assertEqual(self.commercant.telephone, '622111')


class SuppressionCommercantTests(TestCase):
    def setUp(self):
        self.kaloum = Commune.objects.create(nom='Kaloum', code='KAL')
        self.kindia = Commune.objects.create(nom='Kindia', code='KIN')
        self.marche = Marche.objects.create(commune=self.kaloum, nom='Madina')
        self.autre = Marche.objects.create(commune=self.kindia, nom='Central')
        self.boutique = TypePlace.objects.create(marche=self.marche, nom='Boutique')
        Tarif.objects.create(type_place=self.boutique, montant=5000, date_debut=timezone.localdate())
        self.compte = User.objects.create_user(
            username='fatou', password='x', telephone='622111', role=Role.COMMERCANT,
            commune=self.kaloum, marche=self.marche,
        )
        self.commercant = Commercant.objects.create(
            marche=self.marche, nom='Fatou', telephone='622111', user=self.compte,
        )
        self.place = Place.objects.create(
            marche=self.marche, type_place=self.boutique, code='B12', commercant=self.commercant,
        )
        self.exterieur = Commercant.objects.create(marche=self.autre, nom='Mamadou', telephone='622222')
        self.general = User.objects.create_user(
            username='general', password='x', telephone='620000001', role=Role.ADMIN_GENERAL,
        )
        self.admin_commune = User.objects.create_user(
            username='admin_commune', password='x', telephone='620000002',
            role=Role.ADMIN_COMMUNE, commune=self.kaloum,
        )
        self.admin_marche = User.objects.create_user(
            username='admin_marche', password='x', telephone='620000003',
            role=Role.ADMIN_MARCHE, commune=self.kaloum, marche=self.marche,
        )
        self.collecteur = User.objects.create_user(
            username='col', password='x', telephone='620000004', role=Role.COLLECTEUR,
            commune=self.kaloum, marche=self.marche,
        )

    def test_admin_general_supprime_avec_motif(self):
        from tickets.services import emettre_ticket

        ticket, _ = emettre_ticket(self.place, emetteur=self.general)
        self.client.force_login(self.general)
        url = reverse('recensement:commercant_supprimer', args=[self.commercant.pk])
        page = self.client.get(url)
        self.assertContains(page, 'Supprimer Fatou')
        self.assertContains(page, 'Motif')
        response = self.client.post(url, {'motif': 'A quitté le marché'})
        self.assertRedirects(response, reverse('recensement:commercants'))
        self.commercant.refresh_from_db()
        self.place.refresh_from_db()
        self.compte.refresh_from_db()
        self.assertFalse(self.commercant.actif)
        self.assertEqual(self.commercant.motif_suppression, 'A quitté le marché')
        self.assertEqual(self.commercant.supprime_par, self.general)
        self.assertIsNotNone(self.commercant.supprime_le)
        self.assertFalse(self.place.actif)
        self.assertFalse(self.compte.is_active)
        self.assertTrue(Ticket.objects.filter(pk=ticket.pk).exists())
        liste = self.client.get(reverse('recensement:commercants'))
        self.assertNotContains(liste, '622111')
        places = self.client.get(reverse('recensement:places'))
        self.assertContains(places, 'Aucune place.')
        encore = self.client.post(reverse('recensement:commercants'), {
            'nom': 'Awa Diallo',
            'telephone': '622111',
            'type_place': self.boutique.pk,
            'code': 'B12',
            'actif': 'on',
        })
        self.assertEqual(encore.status_code, 302)
        self.assertTrue(Commercant.objects.filter(nom='Awa Diallo', telephone='622111', supprime_le__isnull=True).exists())

    def test_le_motif_est_obligatoire(self):
        self.client.force_login(self.general)
        response = self.client.post(reverse('recensement:commercant_supprimer', args=[self.commercant.pk]), {
            'motif': '   ',
        })
        self.assertEqual(response.status_code, 200)
        self.commercant.refresh_from_db()
        self.assertIsNone(self.commercant.supprime_le)

    def test_admin_commune_supprime_dans_sa_commune_seulement(self):
        self.client.force_login(self.admin_commune)
        response = self.client.post(reverse('recensement:commercant_supprimer', args=[self.commercant.pk]), {
            'motif': 'Doublon',
        })
        self.assertRedirects(response, reverse('recensement:commercants'))
        self.commercant.refresh_from_db()
        self.assertIsNotNone(self.commercant.supprime_le)
        autre = self.client.get(reverse('recensement:commercant_supprimer', args=[self.exterieur.pk]))
        self.assertEqual(autre.status_code, 404)

    def test_les_autres_roles_ne_peuvent_pas_supprimer(self):
        for user in (self.admin_marche, self.collecteur):
            self.client.force_login(user)
            response = self.client.get(reverse('recensement:commercant_supprimer', args=[self.commercant.pk]))
            self.assertEqual(response.status_code, 403)
            liste = self.client.get(reverse('recensement:commercants'))
            self.assertNotContains(liste, reverse('recensement:commercant_supprimer', args=[self.commercant.pk]))
