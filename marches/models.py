from django.conf import settings
from django.db import models


class Commune(models.Model):
    nom = models.CharField(max_length=120)
    code = models.CharField(max_length=20, unique=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    suppression_demandee_le = models.DateTimeField(null=True, blank=True)
    suppression_demandee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='communes_a_supprimer',
    )

    class Meta:
        ordering = ['nom']

    def __str__(self):
        return self.nom


class Marche(models.Model):
    commune = models.ForeignKey(Commune, on_delete=models.PROTECT, related_name='marches')
    nom = models.CharField(max_length=120)
    adresse = models.CharField(max_length=255, blank=True)
    active = models.BooleanField(default=True)
    controle_dettes_bloquant = models.BooleanField(
        default=True,
        help_text='Si coché, un ticket du jour payé avec dettes antérieures n’est pas considéré en règle.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    suppression_demandee_le = models.DateTimeField(null=True, blank=True)
    suppression_demandee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='marches_a_supprimer',
    )

    class Meta:
        ordering = ['commune__nom', 'nom']
        unique_together = [('commune', 'nom')]

    def __str__(self):
        return f'{self.nom} ({self.commune})'


class TypePlace(models.Model):
    marche = models.ForeignKey(Marche, on_delete=models.CASCADE, related_name='types_place')
    nom = models.CharField(max_length=80)
    est_deambulant = models.BooleanField(default=False)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['nom']
        unique_together = [('marche', 'nom')]

    def __str__(self):
        return f'{self.nom} — {self.marche.nom}'


class Tarif(models.Model):
    type_place = models.ForeignKey(TypePlace, on_delete=models.CASCADE, related_name='tarifs')
    montant = models.PositiveIntegerField(help_text='Montant en GNF')
    date_debut = models.DateField()
    date_fin = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-date_debut']

    def __str__(self):
        return f'{self.type_place} : {self.montant} GNF'

    def est_valide_au(self, jour):
        if self.date_debut > jour:
            return False
        if self.date_fin and self.date_fin < jour:
            return False
        return True


class PenaliteParametre(models.Model):
    marche = models.OneToOneField(Marche, on_delete=models.CASCADE, related_name='penalite')
    montant_fixe = models.PositiveIntegerField(default=0, help_text='GNF')
    pourcentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    majoration_par_jour = models.PositiveIntegerField(
        default=0,
        help_text='Majoration quotidienne après clôture (0 = désactivée).',
    )

    def __str__(self):
        return f'Pénalité {self.marche}'

    def calculer(self, montant_ticket):
        extra = int((self.pourcentage or 0) * montant_ticket / 100)
        return int(self.montant_fixe) + extra
