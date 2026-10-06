from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class Role(models.TextChoices):
    ADMIN_GENERAL = 'admin_general', 'Admin général'
    ADMIN_COMMUNE = 'admin_commune', 'Admin commune'
    MAIRE = 'maire', 'Maire'
    COLLECTEUR = 'collecteur', 'Collecteur'
    CONTROLEUR = 'controleur', 'Contrôleur'
    REGISSEUR = 'regisseur', 'Régisseur'
    COMMERCANT = 'commercant', 'Commerçant'


class CustomUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('role', Role.ADMIN_GENERAL)
        extra_fields.setdefault('telephone', extra_fields.get('telephone') or '000000000')
        return super().create_superuser(username, email, password, **extra_fields)


class CustomUser(AbstractUser):
    telephone = models.CharField('téléphone', max_length=20, unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.COLLECTEUR)
    commune = models.ForeignKey(
        'marches.Commune',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='utilisateurs',
    )
    marche = models.ForeignKey(
        'marches.Marche',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='utilisateurs',
    )

    objects = CustomUserManager()

    class Meta:
        verbose_name = 'utilisateur'
        verbose_name_plural = 'utilisateurs'
        ordering = ['username']

    def __str__(self):
        return f'{self.get_full_name() or self.username} ({self.get_role_display()})'

    @property
    def is_admin_general(self):
        return self.role == Role.ADMIN_GENERAL or self.is_superuser

    @property
    def is_admin_commune(self):
        return self.role == Role.ADMIN_COMMUNE

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.role == Role.ADMIN_GENERAL:
            return
        if self.role == Role.ADMIN_COMMUNE and not self.commune_id:
            raise ValidationError({'commune': 'Une commune est obligatoire pour cet administrateur.'})
        if self.role in {Role.COLLECTEUR, Role.CONTROLEUR, Role.REGISSEUR, Role.COMMERCANT} and not self.marche_id:
            raise ValidationError({'marche': 'Un marché est obligatoire pour ce rôle.'})
        if self.marche_id and self.commune_id and self.marche.commune_id != self.commune_id:
            raise ValidationError({'marche': 'Le marché doit appartenir à la commune choisie.'})
        if self.marche_id and not self.commune_id:
            self.commune_id = self.marche.commune_id
