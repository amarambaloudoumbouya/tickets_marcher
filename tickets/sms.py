"""Envoi du numéro de ticket par SMS via l'API Global Flash Send."""

import json
import logging
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger(__name__)

API_SMS = 'https://globalflashsend.com/api/v1/sms'


def numero_e164(telephone):
    """Passe un numéro local guinéen au format E.164 attendu par Global Flash Send."""
    chiffres = re.sub(r'\D', '', telephone or '')
    if chiffres.startswith('00'):
        chiffres = chiffres[2:]
    if chiffres.startswith('224') and len(chiffres) >= 12:
        return f'+{chiffres}'
    if len(chiffres) in (8, 9):
        return f'+224{chiffres}'
    return ''


def texte_ticket(ticket):
    place = f' Place {ticket.place.code}.' if ticket.place_id else ''
    return f'Ticket marché\n{ticket.numero}.{place} {ticket.montant} GNF.'


def mention_sms(ticket):
    if getattr(ticket, 'sms_envoye', False):
        return f' Numéro envoyé par SMS au {ticket.commercant.telephone}.'
    detail = getattr(ticket, 'sms_detail', '')
    return f' {detail}' if detail else ''


def _detail_refus(exc):
    message = ''
    try:
        payload = json.loads(exc.read().decode())
    except Exception:
        payload = None
    if isinstance(payload, dict):
        erreur = payload.get('error')
        if isinstance(erreur, dict):
            message = erreur.get('message') or ''
        elif isinstance(erreur, str):
            message = erreur
        message = message or payload.get('message') or ''
    if message:
        return f'Le SMS n’a pas pu être envoyé : {message}'
    return f'Le SMS n’a pas pu être envoyé (HTTP {getattr(exc, "code", "?")}).'


def envoyer_numero_ticket(ticket):
    """Envoie le numéro du ticket. Retourne (ok, detail). N'envoie rien si l'API n'est pas configurée."""
    if not getattr(settings, 'GFS_SMS_ACTIF', False):
        return False, 'SMS non envoyé : ajoutez GFS_API_KEY dans le .env du serveur, puis redémarrez l’application.'
    destinataire = numero_e164(ticket.commercant.telephone)
    if not destinataire:
        return False, 'SMS non envoyé : le numéro du commerçant est invalide.'
    corps = json.dumps({
        'to': destinataire,
        'text': texte_ticket(ticket),
        'reference': ticket.numero,
    }).encode()
    requete = Request(API_SMS, data=corps, method='POST')
    requete.add_header('Authorization', f'Bearer {settings.GFS_API_KEY}')
    requete.add_header('Content-Type', 'application/json')
    requete.add_header('Accept', 'application/json')
    try:
        with urlopen(requete, timeout=10) as reponse:
            if reponse.status >= 400:
                return False, 'Le SMS n’a pas pu être envoyé.'
    except HTTPError as exc:
        logger.warning('Global Flash Send a refusé le ticket %s', ticket.numero)
        return False, _detail_refus(exc)
    except URLError as exc:
        logger.warning('Global Flash Send est injoignable pour le ticket %s', ticket.numero)
        return False, f'Le SMS n’a pas pu être envoyé : {exc.reason}'
    return True, ''
