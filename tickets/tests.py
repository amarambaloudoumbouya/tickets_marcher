import json
from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.mixins import marches_visibles
from accounts.models import Role
from marches.models import Commune, Marche, PenaliteParametre, Tarif, TypePlace
from recensement.models import Commercant, Place
from tickets.models import Paiement, StatutTicket, Ticket, initiales_commercant
from tickets.services import (
    annuler_ticket,
    callback_paiement,
    cloturer_journee,
    emettre_ticket,
    generer_tickets_du_jour,
    initier_paiement,
    signaler_absence,
    renvoyer_sms_en_attente,
    montant_solde,
    solde_tickets,
    verifier_qr,
)

User = get_user_model()


class BaseSetup(TestCase):
    def setUp(self):
        self.jour = timezone.localdate()
        self.commune = Commune.objects.create(nom='Kaloum', code='KAL', numero_depot='620999000')
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
            commune=self.commune, marche=self.marche, numero_om='624000002',
        )


class TicketEngineTests(BaseSetup):
    def test_numero_porte_initiales_et_place(self):
        self.assertEqual(initiales_commercant('Aïssatou Mariama Diallo'), 'AMD')
        self.assertEqual(initiales_commercant('Mamadou'), 'M')
        self.fatou.nom = 'Fatou Camara'
        self.fatou.save(update_fields=['nom'])
        ticket, _ = emettre_ticket(self.place)
        jour = ticket.date_validite.strftime('%Y%m%d')
        self.assertRegex(
            ticket.numero,
            rf'^TKT-FC-B12-{self.marche.pk}-{jour}-[0-9A-F]{{6}}$',
        )

    @override_settings(GFS_SMS_ACTIF=True, GFS_API_KEY='sk_test_cle')
    def test_sms_envoie_le_numero_de_ticket(self):
        self.fatou.telephone = '622000111'
        self.fatou.save(update_fields=['telephone'])

        class Reponse:
            status = 201

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{}'

        with patch('tickets.sms.urlopen', return_value=Reponse()) as appel:
            with self.captureOnCommitCallbacks(execute=True):
                ticket, created = emettre_ticket(self.place)
        self.assertTrue(created)
        self.assertTrue(ticket.sms_envoye)
        requete = appel.call_args[0][0]
        self.assertEqual(requete.full_url, 'https://globalflashsend.com/api/v1/sms')
        self.assertEqual(requete.get_header('Authorization'), 'Bearer sk_test_cle')
        corps = json.loads(requete.data.decode())
        self.assertEqual(corps['to'], '+224622000111')
        self.assertTrue(corps['text'].startswith(f'Ticket marché\n{ticket.numero}.'))
        self.assertIn('B12', corps['text'])
        self.assertEqual(corps['reference'], ticket.numero)

    @override_settings(GFS_SMS_ACTIF=True, GFS_API_KEY='sk_test_cle')
    def test_renvoi_sms_des_tickets_deja_crees(self):
        class Reponse:
            status = 201

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{}'

        self.fatou.telephone = '622000111'
        self.fatou.save(update_fields=['telephone'])
        with patch('tickets.sms.urlopen', return_value=Reponse()):
            with self.captureOnCommitCallbacks(execute=True):
                ticket, _ = emettre_ticket(self.place)
            Ticket.objects.filter(pk=ticket.pk).update(sms_envoye=False)
            relances = renvoyer_sms_en_attente(self.marche)
            self.assertEqual([t.pk for t in relances], [ticket.pk])
            self.assertTrue(relances[0].sms_envoye)
            self.assertEqual(renvoyer_sms_en_attente(self.marche), [])

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

    def test_retrait_commercant_et_depot_commune(self):
        emettre_ticket(self.place)
        paiement = initier_paiement(self.fatou, initiateur=self.collecteur)
        self.assertEqual(paiement.mode, Paiement.Mode.COMMERCANT)
        self.assertEqual(paiement.numero_retrait, self.fatou.telephone)
        self.assertEqual(paiement.numero_depot, self.commune.numero_depot)

    def test_controleur_paie_sur_son_numero(self):
        emettre_ticket(self.place)
        paiement = initier_paiement(
            self.fatou, initiateur=self.controleur, mode=Paiement.Mode.CONTROLEUR,
        )
        self.assertEqual(paiement.mode, Paiement.Mode.CONTROLEUR)
        self.assertEqual(paiement.numero_retrait, self.controleur.numero_om)
        callback_paiement(paiement, Paiement.Statut.SUCCES)
        paiement.refresh_from_db()
        self.assertEqual(paiement.statut, Paiement.Statut.SUCCES)

    def test_paiement_refuse_sans_numero_de_depot(self):
        self.commune.numero_depot = ''
        self.commune.save(update_fields=['numero_depot'])
        emettre_ticket(self.place)
        with self.assertRaises(ValidationError):
            initier_paiement(self.fatou)

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

    def test_commercant_paye_sur_son_numero(self):
        compte = User.objects.create_user(
            username='fatou', password='x', telephone='622999', role=Role.COMMERCANT,
            commune=self.commune, marche=self.marche,
        )
        self.fatou.user = compte
        self.fatou.save(update_fields=['user'])
        emettre_ticket(self.place)
        self.client.login(username='fatou', password='x')
        page = self.client.get(reverse('tickets:payer'))
        self.assertContains(page, 'Payer')
        self.assertContains(page, 'Paie pour moi')
        reponse = self.client.post(reverse('tickets:payer'), {'action': 'payer'})
        self.assertEqual(reponse.status_code, 302)
        paiement = Paiement.objects.get()
        self.assertEqual(paiement.numero_retrait, self.fatou.telephone)
        self.assertEqual(paiement.numero_depot, '620999000')
        liste = self.client.get(reverse('tickets:tickets'))
        self.assertContains(liste, 'Payé')
        self.assertEqual(self.client.get(reverse('tickets:historique')).status_code, 200)
        self.assertEqual(self.client.get(reverse('tickets:impayes')).status_code, 200)

    def test_controleur_paie_pour_le_commercant_depuis_le_bouton(self):
        emettre_ticket(self.place)
        self.client.login(username='ctrl', password='x')
        page = self.client.get(reverse('tickets:payer') + f'?commercant={self.fatou.pk}')
        self.assertContains(page, 'Paie pour moi')
        reponse = self.client.post(reverse('tickets:payer'), {'commercant': self.fatou.pk})
        self.assertEqual(reponse.status_code, 302)
        paiement = Paiement.objects.get()
        self.assertEqual(paiement.mode, Paiement.Mode.CONTROLEUR)
        self.assertEqual(paiement.numero_retrait, '624000002')
        self.assertEqual(paiement.initiateur, self.controleur)

    def test_le_commercant_peut_aussi_demander_paie_pour_moi(self):
        compte = User.objects.create_user(
            username='fatou', password='x', telephone='622999', role=Role.COMMERCANT,
            commune=self.commune, marche=self.marche,
        )
        self.fatou.user = compte
        self.fatou.save(update_fields=['user'])
        emettre_ticket(self.place)
        self.client.login(username='fatou', password='x')
        reponse = self.client.post(reverse('tickets:payer'), {'action': 'paie_pour_moi'})
        self.assertEqual(reponse.status_code, 302)
        self.assertFalse(Paiement.objects.exists())
        self.client.login(username='ctrl', password='x')
        page = self.client.get(reverse('tickets:payer'))
        self.assertContains(page, 'Demandes des commerçants')
        self.assertContains(page, 'Fatou')
        reponse = self.client.post(reverse('tickets:payer'), {'commercant': self.fatou.pk, 'action': 'payer'})
        self.assertEqual(reponse.status_code, 302)
        paiement = Paiement.objects.get()
        self.assertEqual(paiement.mode, Paiement.Mode.CONTROLEUR)
        self.assertEqual(paiement.numero_retrait, '624000002')
        from tickets.models import DemandePaiement
        demande = DemandePaiement.objects.get()
        self.assertEqual(demande.statut, DemandePaiement.Statut.ACCEPTEE)
        self.assertEqual(demande.paiement, paiement)


class AbsenceTests(BaseSetup):
    def matin(self):
        return timezone.make_aware(datetime.combine(self.jour, time(9, 30)))

    def test_avant_midi_aucun_ticket_n_est_emis(self):
        autre = Commercant.objects.create(marche=self.marche, nom='Mamadou', telephone='622222')
        Place.objects.create(
            marche=self.marche, type_place=self.boutique, code='B13', commercant=autre,
        )
        signaler_absence(self.fatou, '9.509167', '-13.712222', precision='12', maintenant=self.matin())
        crees = generer_tickets_du_jour(self.marche, self.collecteur, jour=self.jour)
        self.assertEqual([ticket.commercant for ticket in crees], [autre])
        self.assertFalse(Ticket.objects.filter(commercant=self.fatou).exists())

    def test_apres_midi_ou_ticket_deja_envoye(self):
        midi = timezone.make_aware(datetime.combine(self.jour, time(12, 0)))
        with self.assertRaises(ValidationError):
            signaler_absence(self.fatou, '9.5', '-13.7', maintenant=midi)
        emettre_ticket(self.place)
        with self.assertRaises(ValidationError):
            signaler_absence(self.fatou, '9.5', '-13.7', maintenant=self.matin())

    def test_la_position_est_obligatoire(self):
        with self.assertRaises(ValidationError):
            signaler_absence(self.fatou, '', '', maintenant=self.matin())

    def test_le_commercant_signale_depuis_son_compte(self):
        compte = User.objects.create_user(
            username='fatou', password='x', telephone='622999', role=Role.COMMERCANT,
            commune=self.commune, marche=self.marche,
        )
        self.fatou.user = compte
        self.fatou.save(update_fields=['user'])
        self.client.login(username='fatou', password='x')
        matin = self.matin()
        with patch('tickets.services.timezone.localtime', return_value=matin):
            page = self.client.get(reverse('tickets:absence'))
            self.assertContains(page, 'Je ne vends pas aujourd')
            reponse = self.client.post(reverse('tickets:absence'), {
                'latitude': '9.509167',
                'longitude': '-13.712222',
                'precision': '20',
            })
        self.assertEqual(reponse.status_code, 302)
        from tickets.models import AbsenceJour
        absence = AbsenceJour.objects.get()
        self.assertEqual(str(absence.latitude), '9.509167')
        self.assertEqual(str(absence.longitude), '-13.712222')
        self.client.login(username='ctrl', password='x')
        suivi = self.client.get(reverse('tickets:absences'))
        self.assertContains(suivi, 'Fatou')
        self.assertContains(suivi, 'openstreetmap.org')
