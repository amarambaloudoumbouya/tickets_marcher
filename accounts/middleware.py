import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect


class InactiviteMiddleware:
    """Ferme la session après un délai sans requête."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        chemin = request.path
        if chemin.startswith('/static/') or chemin.startswith('/media/'):
            return self.get_response(request)
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            maintenant = time.time()
            limite = settings.DUREE_INACTIVITE.total_seconds()
            derniere = request.session.get('derniere_activite')
            if derniere is not None and maintenant - float(derniere) > limite:
                logout(request)
                minutes = int(limite // 60)
                messages.warning(
                    request,
                    f'Vous avez été déconnecté après {minutes} minutes sans activité.',
                )
                return redirect('accounts:login')
            request.session['derniere_activite'] = maintenant
        return self.get_response(request)


class CompteVerrouilleMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        verrouille = request.session.get('compte_verrouille')
        user = getattr(request, 'user', None)
        if verrouille and user is not None and user.is_authenticated:
            chemin = request.path
            autorise = (
                chemin.startswith('/static/')
                or chemin.startswith('/media/')
                or chemin.startswith('/comptes/deverrouiller')
                or chemin.startswith('/comptes/deconnexion')
            )
            if not autorise:
                return redirect('accounts:unlock')
        return self.get_response(request)
