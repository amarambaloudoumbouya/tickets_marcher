from datetime import datetime, time

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from accounts.mixins import scoped_qs
from accounts.models import Role
from tickets.models import JournalAudit, Paiement, StatutTicket, Ticket


_ACTIONS = {
    'commune_creee': 'a créé une commune',
    'commune_suppression_demandee': 'a demandé la suppression d’une commune',
    'commune_supprimee': 'a validé la suppression d’une commune',
    'commune_recuperee': 'a récupéré une commune',
    'marche_cree': 'a créé un marché',
    'marche_suppression_demandee': 'a demandé la suppression d’un marché',
    'marche_supprime': 'a validé la suppression d’un marché',
    'marche_recupere': 'a récupéré un marché',
    'ticket_emis': 'a émis un ticket',
    'generation_tickets': 'a généré les tickets du jour',
    'paiement_initie': 'a initié un paiement',
    'paiement_succes': 'a confirmé un paiement',
    'paiement_echec': 'a enregistré un échec de paiement',
    'ticket_controle': 'a contrôlé un ticket',
    'ticket_annule': 'a annulé un ticket',
    'penalite_annulee': 'a annulé une pénalité',
    'ticket_impaye': 'a marqué un ticket impayé',
    'cloture_journee': 'a clôturé la journée',
}


def role_menu(request):
    user = request.user
    if not user.is_authenticated:
        return {}
    role = user.role
    menu_mairie = role in {
        Role.ADMIN_GENERAL,
        Role.ADMIN_COMMUNE,
        Role.MAIRE,
        Role.REGISSEUR,
    } or user.is_admin_general
    menu_collecteur = role in {Role.COLLECTEUR, Role.ADMIN_GENERAL, Role.ADMIN_COMMUNE}
    menu_controleur = role in {Role.CONTROLEUR, Role.ADMIN_GENERAL, Role.ADMIN_COMMUNE}
    menu_audit = role in {Role.REGISSEUR, Role.ADMIN_GENERAL, Role.ADMIN_COMMUNE, Role.MAIRE}
    voit_tickets = menu_collecteur or menu_mairie or menu_controleur or role == Role.COMMERCANT
    return {
        'menu_mairie': menu_mairie,
        'menu_organisation': role in {Role.ADMIN_GENERAL, Role.ADMIN_COMMUNE} or user.is_admin_general,
        'menu_collecteur': menu_collecteur,
        'menu_controleur': menu_controleur,
        'menu_paiement': role in {Role.COMMERCANT, Role.COLLECTEUR, Role.ADMIN_GENERAL, Role.ADMIN_COMMUNE},
        'menu_cloture': role in {Role.REGISSEUR, Role.ADMIN_GENERAL, Role.ADMIN_COMMUNE},
        'menu_audit': menu_audit,
        'header_notifications': _notifications(user),
        'header_messages': _messages(user, menu_audit),
        'header_notifications_plus': reverse('tickets:impayes') if (menu_collecteur or menu_mairie or menu_controleur) else (
            reverse('tickets:tickets') if voit_tickets else ''
        ),
        'header_notifications_plus_label': 'Voir les impayés' if (menu_collecteur or menu_mairie or menu_controleur) else 'Voir les tickets',
        'header_messages_plus': reverse('tickets:audit') if menu_audit else '',
    }


def _quand(valeur):
    if isinstance(valeur, datetime):
        if timezone.is_naive(valeur):
            return timezone.make_aware(valeur)
        return valeur
    return timezone.make_aware(datetime.combine(valeur, time.min))


def _fiche(user):
    return getattr(user, 'fiche_commercant', None)


def _tickets_visibles(user):
    qs = Ticket.objects.select_related('commercant')
    if user.role == Role.COMMERCANT:
        fiche = _fiche(user)
        return qs.filter(commercant=fiche) if fiche else qs.none()
    return scoped_qs(qs, user)


def _paiements_visibles(user):
    qs = Paiement.objects.select_related('commercant')
    if user.role == Role.COMMERCANT:
        fiche = _fiche(user)
        return qs.filter(commercant=fiche) if fiche else qs.none()
    return scoped_qs(qs, user)


def _notifications(user):
    items = []
    impayes = _tickets_visibles(user).filter(statut=StatutTicket.IMPAYE).order_by('-date_validite')[:6]
    for ticket in impayes:
        items.append({
            'when': _quand(ticket.date_validite),
            'name': ticket.commercant.nom,
            'desc': f'Ticket {ticket.numero} impayé',
            'url': reverse('tickets:ticket_detail', args=[ticket.pk]),
            'icon': 'fa-warning',
            'tone': 'bg-warning',
        })
    paiements = _paiements_visibles(user).exclude(statut=Paiement.Statut.SUCCES).order_by('-created_at')[:6]
    for paiement in paiements:
        if paiement.statut == Paiement.Statut.EN_ATTENTE:
            icon, tone = 'fa-clock-o', 'bg-info'
        else:
            icon, tone = 'fa-times', 'bg-danger'
        peut_payer = user.is_admin_general or user.role in {Role.ADMIN_COMMUNE, Role.COLLECTEUR, Role.COMMERCANT}
        items.append({
            'when': paiement.created_at,
            'name': paiement.commercant.nom,
            'desc': f'{paiement.get_statut_display()} — {paiement.montant} GNF',
            'url': f"{reverse('tickets:payer')}?commercant={paiement.commercant_id}" if peut_payer else '',
            'icon': icon,
            'tone': tone,
        })
    items.sort(key=lambda item: item['when'], reverse=True)
    return items[:8]


def _journal(user):
    qs = JournalAudit.objects.select_related('user')
    if user.is_admin_general:
        return qs
    if user.role == Role.COMMERCANT:
        return qs.filter(user=user)
    if user.role in {Role.ADMIN_COMMUNE, Role.MAIRE} and user.commune_id:
        return qs.filter(Q(user__commune=user.commune) | Q(user__isnull=True))
    if user.marche_id:
        return qs.filter(Q(user__marche=user.marche) | Q(user=user))
    return qs.filter(user=user)


def _texte_audit(entry):
    phrase = _ACTIONS.get(entry.action, entry.action.replace('_', ' '))
    payload = entry.payload or {}
    details = []
    if payload.get('numero'):
        details.append(str(payload['numero']))
    if payload.get('montant') is not None:
        details.append(f"{payload['montant']} GNF")
    if payload.get('nb') is not None:
        details.append(f"{payload['nb']} ticket(s)")
    if payload.get('motif'):
        details.append(str(payload['motif']))
    if details:
        return f"{phrase} — {' · '.join(details)}"
    return phrase


def _url_audit(entry, voit_audit):
    if entry.objet == 'Ticket' and entry.objet_id:
        return reverse('tickets:ticket_detail', args=[entry.objet_id])
    if voit_audit:
        return reverse('tickets:audit')
    return ''


def _messages(user, voit_audit):
    items = []
    for entry in _journal(user)[:8]:
        auteur = entry.user
        items.append({
            'when': entry.created_at,
            'name': (auteur.get_full_name() or auteur.username) if auteur else 'Système',
            'desc': _texte_audit(entry),
            'url': _url_audit(entry, voit_audit),
            'icon': 'fa-user',
            'tone': 'bg-success',
        })
    return items
