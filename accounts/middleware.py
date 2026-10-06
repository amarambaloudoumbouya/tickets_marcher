from django.shortcuts import redirect


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
