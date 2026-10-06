from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from accounts.models import Role
from marches.models import Marche


ROLES_MAIRIE = {Role.ADMIN_GENERAL, Role.ADMIN_COMMUNE, Role.MAIRE, Role.REGISSEUR}
ROLES_BACKOFFICE = {Role.ADMIN_GENERAL, Role.ADMIN_COMMUNE, Role.REGISSEUR, Role.MAIRE}
ROLES_COLLECTE = {Role.ADMIN_GENERAL, Role.ADMIN_COMMUNE, Role.COLLECTEUR}
ROLES_CONTROLE = {Role.ADMIN_GENERAL, Role.ADMIN_COMMUNE, Role.CONTROLEUR}
ROLES_CLOTURE = {Role.ADMIN_GENERAL, Role.ADMIN_COMMUNE, Role.REGISSEUR}
ROLES_PENALITE = {Role.ADMIN_GENERAL, Role.ADMIN_COMMUNE, Role.REGISSEUR}


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    allowed_roles = ()

    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
        if user.is_admin_general:
            return True
        return user.role in self.allowed_roles

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied("Vous n'avez pas acces a cette page.")
        return super().handle_no_permission()


def marches_visibles(user):
    qs = Marche.objects.filter(active=True, suppression_demandee_le__isnull=True).select_related('commune')
    if user.is_admin_general:
        return qs
    if user.role in {Role.ADMIN_COMMUNE, Role.MAIRE} and user.commune_id:
        return qs.filter(commune=user.commune)
    if user.marche_id:
        return qs.filter(pk=user.marche_id)
    return qs.none()


def marches_geres(user):
    qs = Marche.objects.filter(suppression_demandee_le__isnull=True).select_related('commune')
    if user.is_admin_general:
        return qs
    if user.role == Role.ADMIN_COMMUNE and user.commune_id:
        return qs.filter(commune_id=user.commune_id)
    return qs.none()


def marche_courant(request, marche_id=None):
    qs = marches_visibles(request.user)
    if marche_id:
        return get_object_or_404(qs, pk=marche_id)
    sid = request.session.get('marche_id')
    if sid:
        marche = qs.filter(pk=sid).first()
        if marche:
            return marche
    marche = qs.first()
    if marche:
        request.session['marche_id'] = marche.pk
    return marche


def scoped_qs(qs, user, marche_field='marche'):
    if user.is_admin_general:
        return qs
    if user.role in {Role.ADMIN_COMMUNE, Role.MAIRE} and user.commune_id:
        return qs.filter(**{f'{marche_field}__commune': user.commune})
    if user.marche_id:
        return qs.filter(**{marche_field: user.marche})
    return qs.none()
