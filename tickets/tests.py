from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.mixins import marches_visibles
from accounts.models import Role
from marches.models import Commune, Marche, PenaliteParametre, Tarif, TypePlace
from recensement.models import Commercant, Place
from tickets.models import Paiement, StatutTicket, Ticket
from tickets.services import (
    annuler_ticket,
    callback_paiement,
    cloturer_journee,
    emettre_ticket,
    generer_tickets_du_jour,
    initier_paiement,
    montant_solde,
    solde_tickets,
    verifier_qr,
)

User = get_user_model()


class BaseSetup(TestCase):
    def setUp(self):
        self.jour = timezone.localdate()
        self.commune = Commune.objects.create(nom='Kaloum', code='KAL')
        self.marche = Marche.objects.create(commune=self.commune, nom='Madina')
        PenaliteParametre.objects.create(marche=self.marche, montant_fixe=2000, pourcentage=0)
        self.boutique = TypePlace.objects.create(marche=self.marche, nom='Boutique')
        self.deamb_type = TypePlace.objects.create(marche=self.marche, nom='Déambulant', est_deambulant=True)
        Tarif.objects.create(type_place=self.boutique, montant=5000, date_debut=self.jour)
        Tarif.objects.create(type_place=self.deamb_type, montant=2000, date_debut=self.jour)
        self.fatou = Commercant.objects.create(marche=self.marche, nom='Fatou', telephone='622111')
        self.place = Place.objects.create(
            marche=self.marche, type_place=self.boutique, code='B12', commercant=self.fatou
        )
        self.collecteur = User.objects.create_user(
            username='col', password='x', telephone='62001', role=Role.COLLECTEUR,
            commune=self.commune, marche=self.marche,
        )
        self.controleur = User.objects.create_user(
            username='ctrl', password='x', telephone='62002', role=Role.CONTROLEUR,
            commune=self.commune, marche=self.marche,
        )


class TicketEngineTests(BaseSetup):
    def test_unicite_place_jour(self):
        t1, c1 = emettre_ticket(self.place, self.collecteur)
        t2, c2 = emettre_ticket(self.place, self.collecteur)
        self.assertTrue(c1)
        self.assertFalse(c2)
        self.assertEqual(t1.pk, t2.pk)

    def test_unicite_deambulant_personne_marche_jour(self):
        p1 = Place.objects.create(
            marche=self.marche, type_place=self.deamb_type, code='D01',
            commercant=self.fatou, genre=Place.Genre.DEAMBULANT,
        )
        t1, _ = emettre_ticket(p1)
        # même commerçant, autre code, même jour
        p2 = Place.objects.create(
            marche=self.marche, type_place=self.deamb_type, code='D02',
            commercant=self.fatou, genre=Place.Genre.DEAMBULANT,
        )
        t2, created = emettre_ticket(p2)
        self.assertFalse(created)
        self.assertEqual(t1.pk, t2.pk)

    def test_immutabilite_montant(self):
        ticket, _ = emettre_ticket(self.place)
        ticket.montant = 1
        with self.assertRaises(ValidationError):
            ticket.save()

    def test_paiement_uniquement_callback(self):
        ticket, _ = emettre_ticket(self.place)
        paiement = initier_paiement(self.fatou)
        ticket.refresh_from_db()
        self.assertEqual(ticket.statut, StatutTicket.EN_ATTENTE_PAIEMENT)
        ticket.refresh_from_db()
        self.assertNotEqual(ticket.statut, StatutTicket.PAYE)
        callback_paiement(paiement, Paiement.Statut.SUCCES)
        ticket.refresh_from_db()
        self.assertEqual(ticket.statut, StatutTicket.PAYE)

    def test_refus_restaure_emis(self):
        ticket, _ = emettre_ticket(self.place)
        paiement = initier_paiement(self.fatou)
        callback_paiement(paiement, Paiement.Statut.ECHEC)
        ticket.refresh_from_db()
        self.assertEqual(ticket.statut, StatutTicket.EMIS)

    def test_cloture_penalite_et_regularisation(self):
        ticket, _ = emettre_ticket(self.place)
        cloture = cloturer_journee(self.marche)
        ticket.refresh_from_db()
        self.assertEqual(ticket.statut, StatutTicket.IMPAYE)
        self.assertEqual(ticket.montant_penalite, 2000)
        self.assertEqual(ticket.montant_du, 7000)
        self.assertEqual(cloture.tickets_impayes, 1)
        paiement = initier_paiement(self.fatou)
        callback_paiement(paiement, Paiement.Statut.SUCCES)
        ticket.refresh_from_db()
        self.assertEqual(ticket.statut, StatutTicket.REGULARISE)
        self.assertNotEqual(ticket.statut, StatutTicket.PAYE)

    def test_lendemain_nouveau_ticket_plus_dette(self):
        emettre_ticket(self.place)
        cloturer_journee(self.marche)
        demain = self.jour + timedelta(days=1)
        ticket_j1, created = emettre_ticket(self.place, jour=demain)
        self.assertTrue(created)
        self.assertEqual(ticket_j1.montant, 5000)
        dus = solde_tickets(self.fatou, self.marche)
        self.assertEqual(montant_solde(dus), 7000 + 5000)

    def test_lettrage_ancien_vers_recent(self):
        t0, _ = emettre_ticket(self.place)
        cloturer_journee(self.marche)
        demain = self.jour + timedelta(days=1)
        t1, _ = emettre_ticket(self.place, jour=demain)
        paiement = initier_paiement(self.fatou)
        lignes = list(paiement.lignes.select_related('ticket').order_by('id'))
        self.assertEqual(lignes[0].ticket_id, t0.id)
        self.assertEqual(lignes[1].ticket_id, t1.id)
        self.assertEqual(lignes[0].montant_affecte, 7000)
        self.assertEqual(lignes[1].montant_affecte, 5000)

    def test_annulation_tracée(self):
        ticket, _ = emettre_ticket(self.place)
        annuler_ticket(ticket, self.collecteur, 'doublon')
        ticket.refresh_from_db()
        self.assertEqual(ticket.statut, StatutTicket.ANNULE)
        nouveau, created = emettre_ticket(self.place)
        self.assertTrue(created)
        self.assertNotEqual(nouveau.pk, ticket.pk)

    def test_controle_impaye_et_valide(self):
        ticket, _ = emettre_ticket(self.place)
        res = verifier_qr(ticket.qr_payload, self.controleur)
        self.assertEqual(res['resultat'], 'impaye_jour')
        paiement = initier_paiement(self.fatou)
        callback_paiement(paiement, Paiement.Statut.SUCCES)
        ticket.refresh_from_db()
        res = verifier_qr(ticket.qr_payload, self.controleur)
        self.assertEqual(res['resultat'], 'valide')
        ticket.refresh_from_db()
        self.assertEqual(ticket.statut, StatutTicket.CONTROLE)
        res = verifier_qr(ticket.qr_payload, self.controleur)
        self.assertEqual(res['resultat'], 'deja_controle')

    def test_controle_dette_bloquante(self):
        from unittest.mock import patch

        emettre_ticket(self.place)
        cloturer_journee(self.marche)
        demain = self.jour + timedelta(days=1)
        t1, _ = emettre_ticket(self.place, jour=demain)
        t1.statut = StatutTicket.PAYE
        t1.save(update_fields=['statut'])
        with patch('tickets.services.timezone.localdate', return_value=demain):
            res = verifier_qr(t1.qr_payload, self.controleur)
        self.assertEqual(res['resultat'], 'incomplet')

    def test_generation_quotidienne(self):
        crees = generer_tickets_du_jour(self.marche, self.collecteur)
        self.assertEqual(len(crees), 1)
        crees2 = generer_tickets_du_jour(self.marche, self.collecteur)
        self.assertEqual(len(crees2), 0)

    def test_cloisonnement_marche(self):
        autre_c = Commune.objects.create(nom='Kindia', code='KIN')
        autre_m = Marche.objects.create(commune=autre_c, nom='Central')
        vis = marches_visibles(self.collecteur)
        self.assertIn(self.marche, vis)
        self.assertNotIn(autre_m, vis)


class WebSmokeTests(BaseSetup):
    def test_login_et_dashboard_collecteur(self):
        ok = self.client.login(username='col', password='x')
        self.assertTrue(ok)
        r = self.client.get(reverse('site_:dashboard'))
        self.assertEqual(r.status_code, 200)

    def test_collecteur_ne_cree_pas_commune(self):
        self.client.login(username='col', password='x')
        r = self.client.get(reverse('marches:communes'))
        self.assertEqual(r.status_code, 403)
