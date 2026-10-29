"""Envoi du numéro de ticket par SMS via l'API NIMBA SMS."""

import logging
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger(__name__)

API_MESSAGES = 'https://api.nimbasms.com/v1/messages'


def numero_nimba(telephone):
    """Passe un numéro local guinéen au format attendu par NIMBA (indicatif 224)."""
    chiffres = re.sub(r'\D', '', telephone or '')
    if chiffres.startswith('00'):
        chiffres = chiffres[2:]
    if chiffres.startswith('224') and len(chiffres) >= 12:
        return chiffres
    if len(chiffres) in (8, 9):
        return f'224{chiffres}'
    return ''


def texte_ticket(ticket):
    place = f' Place {ticket.place.code}.' if ticket.place_id else ''
    return f'Ticket {ticket.numero}.{place} {ticket.montant} GNF.'


def mention_sms(ticket):
    if getattr(ticket, 'sms_envoye', False):
        return f' Numéro envoyé par SMS au {ticket.commercant.telephone}.'
    detail = getattr(ticket, 'sms_detail', '')
    return f' {detail}' if detail else ''


def envoyer_numero_ticket(ticket):
    """Envoie le numéro du ticket. Retourne (ok, detail). N'envoie rien si l'API n'est pas configurée."""
    if not getattr(settings, 'NIMBA_SMS_ACTIF', False):
        return False, ''
    destinataire = numero_nimba(ticket.commercant.telephone)
    if not destinataire:
        return False, 'SMS non envoyé : le numéro du commerçant est invalide.'
    corps = urlencode(
        [
            ('to', destinataire),
            ('sender_name', settings.NIMBA_SENDER_NAME),
            ('message', texte_ticket(ticket)),
        ]
    ).encode()
    requete = Request(API_MESSAGES, data=corps, method='POST')
    requete.add_header('Authorization', _autorisation())
    requete.add_header('Content-Type', 'application/x-www-form-urlencoded')
    requete.add_header('Accept', 'application/json')
    try:
        with urlopen(requete, timeout=10) as reponse:
            if reponse.status >= 400:
                return False, 'Le SMS n’a pas pu être envoyé.'
    except HTTPError:
        logger.warning('NIMBA SMS a refusé le ticket %s', ticket.numero)
        return False, 'Le SMS n’a pas pu être envoyé.'
    except URLError:
        logger.warning('NIMBA SMS est injoignable pour le ticket %s', ticket.numero)
        return False, 'Le SMS n’a pas pu être envoyé.'
    return True, ''


def _autorisation():
    import base64

    jeton = f'{settings.NIMBA_SERVICE_ID}:{settings.NIMBA_SECRET_TOKEN}'.encode()
    return f'Basic {base64.b64encode(jeton).decode()}'
