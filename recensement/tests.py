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
