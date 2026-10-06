from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from marches.models import PenaliteParametre
from recensement.models import Place
from tickets.models import (
    STATUTS_DU,
    STATUTS_EN_REGLE_JOUR,
    STATUTS_OUVERTS,
    ClotureJournee,
    JournalAudit,
    Paiement,
    PaiementLigne,
    StatutTicket,
    Ticket,
    signer_numero,
)


def audit(user, action, instance=None, **payload):
    objet = ''
    objet_id = None
    if instance is not None:
        objet = instance.__class__.__name__
        objet_id = instance.pk
    return JournalAudit.objects.create(
        user=user if getattr(user, 'is_authenticated', False) else None,
        action=action,
        objet=objet,
        objet_id=objet_id,
        payload=payload,
    )


def tarif_du_jour(type_place, jour=None):
    jour = jour or timezone.localdate()
    tarifs = type_place.tarifs.all()
    for tarif in tarifs:
        if tarif.est_valide_au(jour):
            return tarif.montant
    raise ValidationError(f'Aucun tarif valide au {jour} pour {type_place}.')


def tickets_du_jour(marche, jour=None):
    jour = jour or timezone.localdate()
    return Ticket.objects.filter(marche=marche, date_validite=jour).exclude(statut=StatutTicket.ANNULE)


def ticket_existant(place, jour):
    qs = Ticket.objects.filter(date_validite=jour).exclude(statut=StatutTicket.ANNULE)
    if place.genre == Place.Genre.FIXE and not place.type_place.est_deambulant:
        return qs.filter(place=place).first()
    return qs.filter(
        commercant=place.commercant,
        marche=place.marche,
        type_place__est_deambulant=True,
    ).first()


def emettre_ticket(place, emetteur=None, jour=None, geo=None, photo=None):
    jour = jour or timezone.localdate()
    if not place.actif or not place.commercant.actif:
        raise ValidationError('La place ou le commerçant est inactif.')
    existant = ticket_existant(place, jour)
    if existant:
        return existant, False
    montant = tarif_du_jour(place.type_place, jour)
    ticket = Ticket(
        date_validite=jour,
        marche=place.marche,
        place=place,
        commercant=place.commercant,
        type_place=place.type_place,
        montant=montant,
        emetteur=emetteur,
        photo=photo,
    )
    if geo:
        ticket.geo_lat = geo.get('lat')
        ticket.geo_lng = geo.get('lng')
    ticket.save()
    audit(emetteur, 'ticket_emis', ticket, numero=ticket.numero, montant=montant)
    return ticket, True


def generer_tickets_du_jour(marche, emetteur=None, jour=None):
    jour = jour or timezone.localdate()
    Ticket.objects.filter(
        date_validite__lt=jour,
        statut__in=[StatutTicket.PAYE, StatutTicket.CONTROLE],
    ).update(statut=StatutTicket.EXPIRE)
    crees = []
    for place in Place.objects.filter(marche=marche, actif=True, commercant__actif=True).select_related(
        'type_place', 'commercant'
    ):
        ticket, created = emettre_ticket(place, emetteur=emetteur, jour=jour)
        if created:
            crees.append(ticket)
    audit(emetteur, 'generation_tickets', marche, jour=str(jour), nb=len(crees))
    return crees


def solde_tickets(commercant, marche=None):
    qs = Ticket.objects.filter(commercant=commercant, statut__in=STATUTS_DU).order_by('date_validite', 'id')
    if marche:
        qs = qs.filter(marche=marche)
    return list(qs)


def montant_solde(tickets):
    return sum(t.montant_du for t in tickets)


def has_dettes_anterieures(commercant, marche, jour=None):
    jour = jour or timezone.localdate()
    return Ticket.objects.filter(
        commercant=commercant,
        marche=marche,
        statut=StatutTicket.IMPAYE,
        date_validite__lt=jour,
    ).exists()


@transaction.atomic
def initier_paiement(commercant, initiateur=None, marche=None):
    tickets = solde_tickets(commercant, marche)
    if not tickets:
        raise ValidationError('Aucun montant dû.')
    if Paiement.objects.filter(commercant=commercant, statut=Paiement.Statut.EN_ATTENTE).exists():
        raise ValidationError('Un paiement Orange Money est déjà en cours.')
    montant = montant_solde(tickets)
    paiement = Paiement.objects.create(
        marche=tickets[0].marche,
        commercant=commercant,
        montant=montant,
        initiateur=initiateur,
    )
    for ticket in tickets:
        PaiementLigne.objects.create(
            paiement=paiement,
            ticket=ticket,
            montant_affecte=ticket.montant_du,
            statut_precedent=ticket.statut,
        )
        ticket.statut = StatutTicket.EN_ATTENTE_PAIEMENT
        ticket.save(update_fields=['statut'])
    audit(initiateur, 'paiement_initie', paiement, montant=montant, tickets=[t.numero for t in tickets])
    return paiement


def _restaurer_lignes(paiement):
    for ligne in paiement.lignes.select_related('ticket'):
        ligne.ticket.statut = ligne.statut_precedent
        ligne.ticket.save(update_fields=['statut'])


@transaction.atomic
def callback_paiement(paiement, resultat):
    if paiement.statut != Paiement.Statut.EN_ATTENTE:
        raise ValidationError('Ce paiement a déjà été traité.')
    now = timezone.now()
    if resultat == Paiement.Statut.SUCCES:
        paiement.statut = Paiement.Statut.SUCCES
        paiement.confirmed_at = now
        paiement.save(update_fields=['statut', 'confirmed_at'])
        for ligne in paiement.lignes.select_related('ticket'):
            ticket = ligne.ticket
            if ligne.statut_precedent == StatutTicket.IMPAYE:
                ticket.statut = StatutTicket.REGULARISE
            else:
                ticket.statut = StatutTicket.PAYE
            ticket.save(update_fields=['statut'])
        audit(paiement.initiateur, 'paiement_succes', paiement, montant=paiement.montant)
        return paiement
    if resultat == Paiement.Statut.TIMEOUT:
        paiement.statut = Paiement.Statut.TIMEOUT
    else:
        paiement.statut = Paiement.Statut.ECHEC
    paiement.save(update_fields=['statut'])
    _restaurer_lignes(paiement)
    audit(paiement.initiateur, 'paiement_echec', paiement, resultat=paiement.statut)
    return paiement


def verifier_qr(payload, controleur=None):
    jour = timezone.localdate()
    if not payload or '.' not in payload:
        return {'resultat': 'invalide', 'message': 'QR illisible.'}
    numero, signature = payload.split('.', 1)
    ticket = Ticket.objects.filter(numero=numero).select_related('commercant', 'marche', 'place').first()
    if not ticket or not hmac_ok(numero, signature):
        return {'resultat': 'invalide', 'message': 'Ticket inconnu ou falsifié.'}

    dettes = has_dettes_anterieures(ticket.commercant, ticket.marche, jour)
    deja = bool(ticket.controle_at)

    if ticket.statut == StatutTicket.ANNULE:
        return {'resultat': 'annule', 'ticket': ticket, 'message': 'Annulé'}
    if ticket.statut == StatutTicket.EXPIRE or ticket.date_validite != jour:
        if ticket.statut == StatutTicket.IMPAYE:
            return {
                'resultat': 'impaye',
                'ticket': ticket,
                'message': 'Impayé — pénalité due',
                'dettes': True,
            }
        return {'resultat': 'expire', 'ticket': ticket, 'message': 'Expiré'}
    if ticket.statut == StatutTicket.IMPAYE:
        return {
            'resultat': 'impaye',
            'ticket': ticket,
            'message': 'Impayé — pénalité due',
            'dettes': True,
        }
    if ticket.statut in {StatutTicket.EMIS, StatutTicket.EN_ATTENTE_PAIEMENT}:
        return {
            'resultat': 'impaye_jour',
            'ticket': ticket,
            'message': 'Impayé — pas en règle',
        }
    if ticket.statut in STATUTS_EN_REGLE_JOUR:
        bloquant = ticket.marche.controle_dettes_bloquant
        if dettes and bloquant:
            return {
                'resultat': 'incomplet',
                'ticket': ticket,
                'message': 'Incomplet — pénalité / dette en cours',
                'dettes': True,
            }
        if ticket.statut == StatutTicket.PAYE:
            ticket.statut = StatutTicket.CONTROLE
            ticket.controleur = controleur
            ticket.controle_at = timezone.now()
            ticket.save(update_fields=['statut', 'controleur', 'controle_at'])
            audit(controleur, 'ticket_controle', ticket)
        if deja:
            return {
                'resultat': 'deja_controle',
                'ticket': ticket,
                'message': 'Valide — déjà contrôlé',
            }
        return {'resultat': 'valide', 'ticket': ticket, 'message': 'Valide'}
    if ticket.statut == StatutTicket.REGULARISE and ticket.date_validite == jour:
        return {'resultat': 'valide', 'ticket': ticket, 'message': 'Valide (régularisé)'}
    return {'resultat': 'invalide', 'ticket': ticket, 'message': ticket.get_statut_display()}


def hmac_ok(numero, signature):
    return signature == signer_numero(numero)


@transaction.atomic
def annuler_ticket(ticket, user, motif):
    if ticket.statut not in STATUTS_OUVERTS:
        raise ValidationError('Seuls les tickets émis ou en attente peuvent être annulés.')
    if not motif:
        raise ValidationError('Un motif d’annulation est obligatoire.')
    ticket.statut = StatutTicket.ANNULE
    ticket.motif_annulation = motif
    ticket.annule_par = user
    ticket.save(update_fields=['statut', 'motif_annulation', 'annule_par'])
    audit(user, 'ticket_annule', ticket, motif=motif)
    return ticket


@transaction.atomic
def annuler_penalite(ticket, user, motif):
    if ticket.statut != StatutTicket.IMPAYE:
        raise ValidationError('La pénalité ne peut être annulée que sur un ticket impayé.')
    if not motif:
        raise ValidationError('Un motif est obligatoire.')
    ticket.montant_penalite = 0
    ticket.majoration = 0
    ticket.penalite_annulee = True
    ticket.motif_annulation_penalite = motif
    ticket.save(update_fields=['montant_penalite', 'majoration', 'penalite_annulee', 'motif_annulation_penalite'])
    audit(user, 'penalite_annulee', ticket, motif=motif)
    return ticket


def _param_penalite(marche):
    param, _ = PenaliteParametre.objects.get_or_create(marche=marche)
    return param


@transaction.atomic
def cloturer_journee(marche, auteur=None, jour=None):
    jour = jour or timezone.localdate()
    if ClotureJournee.objects.filter(marche=marche, date=jour).exists():
        raise ValidationError('Cette journée est déjà clôturée.')

    pendings = Paiement.objects.filter(marche=marche, statut=Paiement.Statut.EN_ATTENTE).filter(
        Q(created_at__date=jour) | Q(lignes__ticket__date_validite=jour)
    ).distinct()
    for paiement in pendings:
        callback_paiement(paiement, Paiement.Statut.TIMEOUT)

    param = _param_penalite(marche)
    ouverts = Ticket.objects.select_for_update().filter(
        marche=marche, date_validite=jour, statut__in=STATUTS_OUVERTS
    )
    penalites = 0
    for ticket in ouverts:
        ticket.montant_penalite = param.calculer(ticket.montant)
        ticket.statut = StatutTicket.IMPAYE
        ticket.save(update_fields=['montant_penalite', 'statut'])
        penalites += ticket.montant_penalite
        audit(auteur, 'ticket_impaye', ticket, penalite=ticket.montant_penalite)

    if param.majoration_par_jour:
        anciens = Ticket.objects.select_for_update().filter(
            marche=marche, statut=StatutTicket.IMPAYE, date_validite__lt=jour
        )
        for ticket in anciens:
            ticket.majoration += param.majoration_par_jour
            ticket.save(update_fields=['majoration'])

    qs = Ticket.objects.filter(marche=marche, date_validite=jour)
    payes = qs.filter(statut__in=[StatutTicket.PAYE, StatutTicket.CONTROLE])
    regularises_jour = Ticket.objects.filter(
        marche=marche,
        statut=StatutTicket.REGULARISE,
        lignes_paiement__paiement__confirmed_at__date=jour,
    ).distinct()
    montant_om = (
        Paiement.objects.filter(marche=marche, statut=Paiement.Statut.SUCCES, confirmed_at__date=jour).aggregate(
            s=Sum('montant')
        )['s']
        or 0
    )
    penalites_encaissees = (
        Ticket.objects.filter(
            marche=marche,
            statut=StatutTicket.REGULARISE,
            lignes_paiement__paiement__confirmed_at__date=jour,
        )
        .distinct()
        .aggregate(s=Sum(F('montant_penalite') + F('majoration')))['s']
        or 0
    )

    cloture = ClotureJournee.objects.create(
        marche=marche,
        date=jour,
        tickets_emis=qs.exclude(statut=StatutTicket.ANNULE).count(),
        tickets_payes=payes.count(),
        tickets_impayes=qs.filter(statut=StatutTicket.IMPAYE).count(),
        tickets_regularises=regularises_jour.count(),
        tickets_annules=qs.filter(statut=StatutTicket.ANNULE).count(),
        penalites_emises=penalites,
        penalites_encaissees=penalites_encaissees,
        montant_tarifs_payes=payes.aggregate(s=Sum('montant'))['s'] or 0,
        montant_om=montant_om,
        auteur=auteur,
    )
    audit(auteur, 'cloture_journee', cloture, marche=marche.nom, date=str(jour))
    return cloture
