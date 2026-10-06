from urllib.parse import quote
from xml.sax.saxutils import escape

from django import template

register = template.Library()

_COLORS = ('0f2f24', '1c6b4a', '188ae2', '5b69bc', 'ea4335', 'fbbc05')


def _initiales(user):
    nom = (user.get_full_name() or user.get_username() or '?').strip()
    morceaux = [partie for partie in nom.split() if partie]
    if len(morceaux) >= 2:
        lettres = morceaux[0][0] + morceaux[1][0]
    else:
        lettres = nom[:2]
    return escape(lettres.upper())


@register.simple_tag
def user_avatar(user):
    fiche = getattr(user, 'fiche_commercant', None)
    photo = getattr(fiche, 'photo', None)
    if photo:
        return photo.url
    couleur = _COLORS[sum(ord(caractere) for caractere in user.get_username()) % len(_COLORS)]
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80">'
        f'<rect width="80" height="80" fill="#{couleur}"/>'
        '<text x="50%" y="54%" text-anchor="middle" fill="#ffffff" '
        'font-family="sans-serif" font-size="32" font-weight="600">'
        f'{_initiales(user)}</text></svg>'
    )
    return 'data:image/svg+xml,' + quote(svg)


_LABELS_AUDIT = {
    'nom': 'Nom',
    'numero': 'Numéro',
    'montant': 'Montant',
    'nb': 'Nombre',
    'motif': 'Motif',
    'tickets': 'Tickets',
    'resultat': 'Résultat',
    'penalite': 'Pénalité',
    'marche': 'Marché',
    'date': 'Date',
    'jour': 'Jour',
}


@register.filter
def detail_audit(payload):
    if not payload:
        return '—'
    parts = []
    for key, value in payload.items():
        if isinstance(value, list):
            value = ', '.join(str(item) for item in value)
        if key in {'montant', 'penalite'}:
            value = f'{value} GNF'
        parts.append(f'{_LABELS_AUDIT.get(key, key)} : {value}')
    return ' · '.join(parts)
