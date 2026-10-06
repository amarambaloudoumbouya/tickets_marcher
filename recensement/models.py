from django.conf import settings
from django.db import models


class Commercant(models.Model):
    marche = models.ForeignKey('marches.Marche', on_delete=models.PROTECT, related_name='commercants')
    nom = models.CharField(max_length=150)
    telephone = models.CharField('téléphone Orange Money', max_length=20)
    photo = models.ImageField(upload_to='commercants/', blank=True, null=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fiche_commercant',
    )
    actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='commercants_crees',
    )

    class Meta:
        ordering = ['nom']
        unique_together = [('marche', 'telephone')]
        verbose_name = 'commerçant'
        verbose_name_plural = 'commerçants'

    def __str__(self):
        return f'{self.nom} ({self.telephone})'


class Place(models.Model):
    class Genre(models.TextChoices):
        FIXE = 'fixe', 'Place fixe'
        DEAMBULANT = 'deambulant', 'Déambulant'

    marche = models.ForeignKey('marches.Marche', on_delete=models.PROTECT, related_name='places')
    type_place = models.ForeignKey('marches.TypePlace', on_delete=models.PROTECT, related_name='places')
    genre = models.CharField(max_length=20, choices=Genre.choices, default=Genre.FIXE)
    code = models.CharField(max_length=40, help_text='Numéro de boutique / table, ou code déambulant')
    commercant = models.ForeignKey(Commercant, on_delete=models.PROTECT, related_name='places')
    photo = models.ImageField(upload_to='places/', blank=True, null=True)
    actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='places_crees',
    )

    class Meta:
        ordering = ['code']
        unique_together = [('marche', 'code')]

    def __str__(self):
        return f'{self.code} — {self.commercant.nom}'

    def save(self, *args, **kwargs):
        if self.type_place_id and self.type_place.est_deambulant:
            self.genre = self.Genre.DEAMBULANT
        super().save(*args, **kwargs)
