import hmac
import hashlib
import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class StatutTicket(models.TextChoices):
    EMIS = 'emis', 'Émis'
    EN_ATTENTE_PAIEMENT = 'en_attente_paiement', 'En attente de paiement'
    PAYE = 'paye', 'Payé'
    CONTROLE = 'controle', 'Contrôlé'
    IMPAYE = 'impaye', 'Impayé'
    REGULARISE = 'regularise', 'Régularisé'
    ANNULE = 'annule', 'Annulé'
    EXPIRE = 'expire', 'Expiré'


STATUTS_OUVERTS = {StatutTicket.EMIS, StatutTicket.EN_ATTENTE_PAIEMENT}
STATUTS_DU = {StatutTicket.EMIS, StatutTicket.EN_ATTENTE_PAIEMENT, StatutTicket.IMPAYE}
STATUTS_EN_REGLE_JOUR = {StatutTicket.PAYE, StatutTicket.CONTROLE}
IMMUTABLE_FIELDS = (
    'numero',
    'date_validite',
    'montant',
    'marche_id',
    'place_id',
    'commercant_id',
    'type_place_id',
)


def signer_numero(numero):
    digest = hmac.new(
        settings.SECRET_KEY.encode(),
        numero.encode(),
        hashlib.sha256,
    ).hexdigest()[:12]
    return digest


class Ticket(models.Model):
    numero = models.CharField(max_length=40, unique=True, editable=False)
    signature = models.CharField(max_length=16, editable=False)
    date_validite = models.DateField()
    marche = models.ForeignKey('marches.Marche', on_delete=models.PROTECT, related_name='tickets')
    place = models.ForeignKey(
        'recensement.Place',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='tickets',
    )
    commercant = models.ForeignKey(
        'recensement.Commercant',
        on_delete=models.PROTECT,
        related_name='tickets',
    )
    type_place = models.ForeignKey('marches.TypePlace', on_delete=models.PROTECT, related_name='tickets')
    montant = models.PositiveIntegerField()
    montant_penalite = models.PositiveIntegerField(default=0)
    majoration = models.PositiveIntegerField(default=0)
    statut = models.CharField(max_length=24, choices=StatutTicket.choices, default=StatutTicket.EMIS)
    emetteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tickets_emis',
    )
    geo_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    geo_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    photo = models.ImageField(upload_to='tickets/', blank=True, null=True)
    motif_annulation = models.TextField(blank=True)
    annule_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tickets_annules',
    )
    controleur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tickets_controles',
    )
    controle_at = models.DateTimeField(null=True, blank=True)
    penalite_annulee = models.BooleanField(default=False)
    motif_annulation_penalite = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_validite', '-id']
        indexes = [
            models.Index(fields=['date_validite', 'statut']),
            models.Index(fields=['numero']),
        ]

    def __str__(self):
        return self.numero

    @property
    def montant_du(self):
        if self.statut not in STATUTS_DU:
            return 0
        return self.montant + self.montant_penalite + self.majoration

    @property
    def qr_payload(self):
        return f'{self.numero}.{self.signature}'

    def save(self, *args, **kwargs):
        if self.pk:
            ancien = Ticket.objects.get(pk=self.pk)
            for field in IMMUTABLE_FIELDS:
                if getattr(ancien, field) != getattr(self, field):
                    raise ValidationError(f'Le champ {field} d’un ticket ne peut pas être modifié.')
        elif not self.numero:
            jour = self.date_validite.strftime('%Y%m%d')
            alea = secrets.token_hex(3).upper()
            self.numero = f'TKT-{self.marche_id}-{jour}-{alea}'
            self.signature = signer_numero(self.numero)
        super().save(*args, **kwargs)


class Paiement(models.Model):
    class Statut(models.TextChoices):
        EN_ATTENTE = 'en_attente', 'En attente'
        SUCCES = 'succes', 'Succès'
        ECHEC = 'echec', 'Échec'
        TIMEOUT = 'timeout', 'Timeout'

    reference = models.CharField(max_length=40, unique=True, editable=False)
    marche = models.ForeignKey('marches.Marche', on_delete=models.PROTECT, related_name='paiements')
    commercant = models.ForeignKey('recensement.Commercant', on_delete=models.PROTECT, related_name='paiements')
    montant = models.PositiveIntegerField()
    statut = models.CharField(max_length=16, choices=Statut.choices, default=Statut.EN_ATTENTE)
    mock_token = models.CharField(max_length=64, unique=True)
    initiateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='paiements_inities',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.reference

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f'OM-{timezone.localdate().strftime("%Y%m%d")}-{secrets.token_hex(4).upper()}'
        if not self.mock_token:
            self.mock_token = secrets.token_urlsafe(24)
        super().save(*args, **kwargs)


class PaiementLigne(models.Model):
    paiement = models.ForeignKey(Paiement, on_delete=models.CASCADE, related_name='lignes')
    ticket = models.ForeignKey(Ticket, on_delete=models.PROTECT, related_name='lignes_paiement')
    montant_affecte = models.PositiveIntegerField()
    statut_precedent = models.CharField(max_length=24, choices=StatutTicket.choices)

    class Meta:
        unique_together = [('paiement', 'ticket')]


class ClotureJournee(models.Model):
    marche = models.ForeignKey('marches.Marche', on_delete=models.PROTECT, related_name='clotures')
    date = models.DateField()
    tickets_emis = models.PositiveIntegerField(default=0)
    tickets_payes = models.PositiveIntegerField(default=0)
    tickets_impayes = models.PositiveIntegerField(default=0)
    tickets_regularises = models.PositiveIntegerField(default=0)
    tickets_annules = models.PositiveIntegerField(default=0)
    penalites_emises = models.PositiveIntegerField(default=0)
    penalites_encaissees = models.PositiveIntegerField(default=0)
    montant_tarifs_payes = models.PositiveIntegerField(default=0)
    montant_om = models.PositiveIntegerField(default=0)
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('marche', 'date')]
        ordering = ['-date']

    def __str__(self):
        return f'Clôture {self.marche} {self.date}'


class JournalAudit(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audits',
    )
    action = models.CharField(max_length=80)
    objet = models.CharField(max_length=80, blank=True)
    objet_id = models.PositiveIntegerField(null=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.action} ({self.created_at:%Y-%m-%d %H:%M})'
