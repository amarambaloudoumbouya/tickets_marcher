import time

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Role
from marches.models import Commune, Marche


User = get_user_model()


class HierarchieCreationTests(TestCase):
    def setUp(self):
        self.kaloum = Commune.objects.create(nom='Kaloum', code='KAL')
        self.kindia = Commune.objects.create(nom='Kindia', code='KIN')
        self.madina = Marche.objects.create(commune=self.kaloum, nom='Madina')
        self.central = Marche.objects.create(commune=self.kindia, nom='Central')
        self.general = User.objects.create_user(
            username='general', password='x', telephone='620000001', role=Role.ADMIN_GENERAL,
        )
        self.admin_commune = User.objects.create_user(
            username='admin_commune', password='x', telephone='620000002',
            role=Role.ADMIN_COMMUNE, commune=self.kaloum,
        )
        self.admin_marche = User.objects.create_user(
            username='admin_marche', password='x', telephone='620000003',
            role=Role.ADMIN_MARCHE, commune=self.kaloum, marche=self.madina,
        )
        self.autre_commune = User.objects.create_user(
            username='admin_kindia', password='x', telephone='620000004',
            role=Role.ADMIN_COMMUNE, commune=self.kindia,
        )

    def _compte(self, **extra):
        data = {
            'first_name': 'Awa',
            'last_name': 'Diallo',
            'email': '',
            'password1': 'Secret123!',
            'password2': 'Secret123!',
            'is_active': 'on',
        }
        data.update(extra)
        return data

    def test_admin_general_cree_une_commune_et_son_admin(self):
        self.client.force_login(self.general)
        response = self.client.post(reverse('marches:communes'), {
            'nom': 'Matam',
            'code': 'MAT',
            'numero_depot': '620100010',
            'active': 'on',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Commune.objects.filter(code='MAT').exists())
        liste = self.client.get(reverse('marches:communes'))
        self.assertContains(liste, 'Orange Money')
        self.assertContains(liste, '620100010')

        response = self.client.post(reverse('site_:user_create'), self._compte(
            username='admin_matam',
            telephone='620000010',
            role=Role.ADMIN_COMMUNE,
            commune=self.kaloum.pk,
        ))
        self.assertEqual(response.status_code, 302)
        cree = User.objects.get(username='admin_matam')
        self.assertEqual(cree.role, Role.ADMIN_COMMUNE)
        self.assertEqual(cree.commune, self.kaloum)
        self.assertIsNone(cree.marche_id)

    def test_admin_general_cree_aussi_marches_et_tous_les_roles(self):
        self.client.force_login(self.general)
        response = self.client.post(reverse('marches:marches'), {
            'commune': self.kindia.pk,
            'nom': 'Nouveau',
            'adresse': '',
            'active': 'on',
            'controle_dettes_bloquant': 'on',
        })
        self.assertEqual(response.status_code, 302)
        marche = Marche.objects.get(nom='Nouveau')
        self.assertEqual(marche.commune, self.kindia)

        response = self.client.post(reverse('site_:user_create'), self._compte(
            username='col_general',
            telephone='620000011',
            role=Role.COLLECTEUR,
            commune=self.kaloum.pk,
            marche=self.madina.pk,
        ))
        self.assertEqual(response.status_code, 302)
        collecteur = User.objects.get(username='col_general')
        self.assertEqual(collecteur.role, Role.COLLECTEUR)
        self.assertEqual(collecteur.marche, self.madina)

        response = self.client.post(reverse('site_:user_create'), self._compte(
            username='autre_general',
            telephone='620000017',
            role=Role.ADMIN_GENERAL,
        ))
        self.assertEqual(response.status_code, 302)
        autre = User.objects.get(username='autre_general')
        self.assertEqual(autre.role, Role.ADMIN_GENERAL)
        self.assertIsNone(autre.commune_id)
        self.assertIsNone(autre.marche_id)

        page = self.client.get(reverse('marches:marches'))
        self.assertContains(page, 'Nouveau marché')
        self.assertContains(self.client.get(reverse('site_:user_create')), 'Admin marché')

    def test_admin_commune_cree_marche_maire_et_admin_marche(self):
        self.client.force_login(self.admin_commune)
        response = self.client.post(reverse('marches:marches'), {
            'commune': self.kindia.pk,
            'nom': 'Niger',
            'adresse': 'Centre',
            'active': 'on',
            'controle_dettes_bloquant': 'on',
        })
        self.assertEqual(response.status_code, 302)
        marche = Marche.objects.get(nom='Niger')
        self.assertEqual(marche.commune, self.kaloum)

        response = self.client.post(reverse('site_:user_create'), self._compte(
            username='maire_kaloum',
            telephone='620000012',
            role=Role.MAIRE,
            commune=self.kindia.pk,
            marche=self.madina.pk,
        ))
        self.assertEqual(response.status_code, 302)
        maire = User.objects.get(username='maire_kaloum')
        self.assertEqual(maire.role, Role.MAIRE)
        self.assertEqual(maire.commune, self.kaloum)
        self.assertIsNone(maire.marche_id)

        response = self.client.post(reverse('site_:user_create'), self._compte(
            username='admin_niger',
            telephone='620000013',
            role=Role.ADMIN_MARCHE,
            marche=marche.pk,
        ))
        self.assertEqual(response.status_code, 302)
        admin = User.objects.get(username='admin_niger')
        self.assertEqual(admin.role, Role.ADMIN_MARCHE)
        self.assertEqual(admin.marche, marche)
        self.assertEqual(admin.commune, self.kaloum)

        page = self.client.get(reverse('site_:dashboard'))
        self.assertNotContains(page, 'Communes</span>')
        self.assertContains(page, 'Marchés')

    def test_admin_commune_ne_cree_pas_un_admin_general(self):
        self.client.force_login(self.admin_commune)
        response = self.client.post(reverse('site_:user_create'), self._compte(
            username='autre_admin',
            telephone='620000014',
            role=Role.ADMIN_GENERAL,
        ))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='autre_admin').exists())
        self.assertEqual(self.client.get(reverse('marches:communes')).status_code, 403)

    def test_admin_marche_cree_les_membres_de_son_marche(self):
        self.client.force_login(self.admin_marche)
        response = self.client.post(reverse('site_:user_create'), self._compte(
            username='collecteur_madina',
            telephone='620000015',
            role=Role.COLLECTEUR,
            commune=self.kindia.pk,
            marche=self.central.pk,
        ))
        self.assertEqual(response.status_code, 302)
        collecteur = User.objects.get(username='collecteur_madina')
        self.assertEqual(collecteur.role, Role.COLLECTEUR)
        self.assertEqual(collecteur.marche, self.madina)
        self.assertEqual(collecteur.commune, self.kaloum)

        response = self.client.post(reverse('site_:user_create'), self._compte(
            username='second_admin',
            telephone='620000016',
            role=Role.ADMIN_MARCHE,
        ))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='second_admin').exists())
        self.assertEqual(self.client.post(reverse('marches:marches'), {
            'commune': self.kaloum.pk,
            'nom': 'Interdit',
            'adresse': '',
        }).status_code, 403)

        page = self.client.get(reverse('site_:dashboard'))
        self.assertContains(page, 'Utilisateurs')
        self.assertNotContains(page, '>Marchés<')
        self.assertNotContains(page, '>Communes<')

    def test_chaque_admin_ne_voit_que_son_perimetre(self):
        self.client.force_login(self.admin_commune)
        page = self.client.get(reverse('site_:utilisateurs'))
        self.assertContains(page, 'admin_marche')
        self.assertNotContains(page, 'admin_kindia')
        self.assertEqual(
            self.client.get(reverse('site_:user_update', args=[self.autre_commune.pk])).status_code,
            404,
        )

        self.client.force_login(self.admin_marche)
        page = self.client.get(reverse('site_:utilisateurs'))
        self.assertContains(page, 'admin_marche')
        self.assertNotContains(page, 'admin_commune')
        self.assertNotContains(page, 'maire')


class InactiviteSessionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='session', password='x', telephone='620888001', role=Role.ADMIN_GENERAL,
        )

    def test_quinze_minutes_sans_action_deconnecte(self):
        self.client.force_login(self.user)
        session = self.client.session
        session['derniere_activite'] = time.time() - 16 * 60
        session.save()
        response = self.client.get(reverse('site_:dashboard'), follow=True)
        self.assertEqual(response.redirect_chain[0][0], reverse('accounts:login'))
        self.assertContains(response, '15 minutes sans activité')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_une_action_recente_laisse_la_session_ouverte(self):
        self.client.force_login(self.user)
        session = self.client.session
        session['derniere_activite'] = time.time() - 5 * 60
        session.save()
        response = self.client.get(reverse('site_:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('_auth_user_id', self.client.session)
