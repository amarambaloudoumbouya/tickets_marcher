from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Q

from accounts.models import Role

User = get_user_model()


def _prenom_nom(nom):
    parties = (nom or '').split()
    if not parties:
        return 'Commerçant', ''
    return parties[0][:150], ' '.join(parties[1:])[:150]


def _liberer_identifiant(valeur, sauf_user_id=None):
    """Libère un téléphone ou un identifiant détenu par un compte inactif."""
    qs = User.objects.filter(Q(telephone=valeur) | Q(username=valeur))
    if sauf_user_id:
        qs = qs.exclude(pk=sauf_user_id)
    if qs.filter(is_active=True).exists():
        raise ValidationError('Ce numéro est déjà utilisé par un autre compte.')
    for user in qs:
        user.username = f'inactif-{user.pk}'
        user.telephone = f'x{user.pk}'[:20]
        user.save(update_fields=['username', 'telephone'])


def assurer_compte_commercant(commercant, ancien_telephone=None):
    """Crée ou met à jour le compte du commerçant.

    Le mot de passe initial est le numéro de téléphone. Il n’est renvoyé
    qu’à la création, pour être communiqué une seule fois.
    """
    if commercant.supprime_le:
        return commercant.user, None
    prenom, nom = _prenom_nom(commercant.nom)
    marche = commercant.marche
    if commercant.user_id:
        user = commercant.user
        telephone = commercant.telephone
        renomme = bool(ancien_telephone and user.username == ancien_telephone and ancien_telephone != telephone)
        if user.telephone != telephone or renomme:
            _liberer_identifiant(telephone, sauf_user_id=user.pk)
        if renomme:
            user.username = telephone
        user.telephone = telephone
        user.first_name = prenom
        user.last_name = nom
        user.role = Role.COMMERCANT
        user.marche = marche
        user.commune = marche.commune
        user.is_active = bool(commercant.actif)
        user.save()
        return user, None

    _liberer_identifiant(commercant.telephone)
    user = User.objects.create_user(
        username=commercant.telephone,
        password=commercant.telephone,
        telephone=commercant.telephone,
        first_name=prenom,
        last_name=nom,
        role=Role.COMMERCANT,
        commune=marche.commune,
        marche=marche,
        is_active=bool(commercant.actif),
    )
    commercant.user = user
    commercant.save(update_fields=['user'])
    return user, commercant.telephone
