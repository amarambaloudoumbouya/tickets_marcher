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


def _fiche(user):
    try:
        return user.fiche_commercant
    except User.fiche_commercant.RelatedObjectDoesNotExist:
        return None


def _comptes_du_numero(valeur, sauf_user_id=None):
    qs = User.objects.filter(Q(telephone=valeur) | Q(username=valeur))
    if sauf_user_id:
        return qs.exclude(pk=sauf_user_id)
    return qs


def _liberer_identifiant(valeur, sauf_user_id=None):
    """Libère un téléphone ou un identifiant détenu par un compte inactif."""
    qs = _comptes_du_numero(valeur, sauf_user_id)
    if qs.filter(is_active=True).exists():
        raise ValidationError('Ce numéro est déjà utilisé par un autre compte.')
    for user in qs:
        user.username = f'inactif-{user.pk}'
        user.telephone = f'x{user.pk}'[:20]
        user.save(update_fields=['username', 'telephone'])


def _identifiants_libres(telephone, commercant_id):
    """Identifiant de secours quand le numéro appartient déjà à un autre compte."""
    for n in range(1, 50):
        username = f'{telephone}-{commercant_id}' if n == 1 else f'{telephone}-{commercant_id}-{n}'
        username = username[:150]
        tel_compte = f'c{commercant_id}' if n == 1 else f'c{commercant_id}x{n}'
        tel_compte = tel_compte[:20]
        if not User.objects.filter(Q(username=username) | Q(telephone=tel_compte)).exists():
            return username, tel_compte
    raise ValidationError('Impossible de créer un identifiant unique pour ce commerçant.')


def _creer_compte(commercant, username, telephone, password):
    prenom, nom = _prenom_nom(commercant.nom)
    marche = commercant.marche
    user = User.objects.create_user(
        username=username,
        password=password,
        telephone=telephone,
        first_name=prenom,
        last_name=nom,
        role=Role.COMMERCANT,
        commune=marche.commune,
        marche=marche,
        is_active=bool(commercant.actif),
    )
    commercant.user = user
    commercant.save(update_fields=['user'])
    return user, password


def _rattacher_commercant_existant(commercant, comptes):
    """Relie la fiche à un compte commerçant déjà ouvert avec ce numéro."""
    for user in comptes:
        if user.role != Role.COMMERCANT:
            continue
        fiche = _fiche(user)
        if fiche and fiche.pk != commercant.pk:
            continue
        prenom, nom = _prenom_nom(commercant.nom)
        user.first_name = prenom
        user.last_name = nom
        user.marche = commercant.marche
        user.commune = commercant.marche.commune
        user.is_active = bool(commercant.actif)
        user.save()
        commercant.user = user
        commercant.save(update_fields=['user'])
        return user
    return None


def assurer_compte_commercant(commercant, ancien_telephone=None, tolere_conflit=False):
    """Crée ou met à jour le compte du commerçant.

    Le mot de passe initial est le numéro de téléphone. Il n’est renvoyé
    qu’à la création, pour être communiqué une seule fois.

    tolere_conflit sert à la migration : si le numéro est déjà pris, le
    compte est rattaché ou créé avec un autre identifiant, sans interrompre
    le déploiement.
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

    actifs = list(_comptes_du_numero(commercant.telephone).filter(is_active=True))
    if actifs:
        if not tolere_conflit:
            raise ValidationError('Ce numéro est déjà utilisé par un autre compte.')
        rattache = _rattacher_commercant_existant(commercant, actifs)
        if rattache:
            return rattache, None
        username, tel_compte = _identifiants_libres(commercant.telephone, commercant.pk)
        return _creer_compte(commercant, username, tel_compte, commercant.telephone)

    _liberer_identifiant(commercant.telephone)
    return _creer_compte(
        commercant,
        commercant.telephone,
        commercant.telephone,
        commercant.telephone,
    )
