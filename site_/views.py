from io import BytesIO

import qrcode
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, ProtectedError, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, ListView, TemplateView, UpdateView, View

from accounts.forms import UserForm
from marches.forms import CommuneForm, MarcheForm, PenaliteForm, TarifForm, TypePlaceForm
from accounts.mixins import (
    ROLES_BACKOFFICE,
    ROLES_CLOTURE,
    ROLES_COLLECTE,
    ROLES_CONTROLE,
    ROLES_MAIRIE,
    ROLES_PENALITE,
    RoleRequiredMixin,
    marche_courant,
    marches_geres,
    marches_visibles,
    scoped_qs,
)
from accounts.models import CustomUser, Role
from marches.models import Commune, Marche, PenaliteParametre, Tarif, TypePlace
from recensement.forms import CommercantForm, PlaceForm
from recensement.models import Commercant, Place
from tickets.forms import AnnulationForm, ScanForm
from tickets.models import ClotureJournee, JournalAudit, Paiement, StatutTicket, Ticket
from tickets.services import (
    annuler_penalite,
    annuler_ticket,
    audit,
    callback_paiement,
    cloturer_journee,
    emettre_ticket,
    generer_tickets_du_jour,
    initier_paiement,
    montant_solde,
    solde_tickets,
    verifier_qr,
)


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'site_/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        marche = marche_courant(self.request)
        jour = timezone.localdate()
        ctx['marche'] = marche
        ctx['marches'] = marches_visibles(user)
        ctx['jour'] = jour
        if not marche:
            return ctx
        tickets = Ticket.objects.filter(marche=marche, date_validite=jour)
        ctx['nb_emis'] = tickets.exclude(statut=StatutTicket.ANNULE).count()
        ctx['nb_payes'] = tickets.filter(statut__in=[StatutTicket.PAYE, StatutTicket.CONTROLE]).count()
        ctx['nb_impayes'] = Ticket.objects.filter(marche=marche, statut=StatutTicket.IMPAYE).count()
        ctx['montant_om'] = (
            Paiement.objects.filter(marche=marche, statut=Paiement.Statut.SUCCES, confirmed_at__date=jour).aggregate(
                s=Sum('montant')
            )['s']
            or 0
        )
        ctx['cloture'] = ClotureJournee.objects.filter(marche=marche, date=jour).first()
        detail = tickets
        paiements = Paiement.objects.filter(marche=marche).select_related('commercant')
        ctx['detail_personnel'] = False
        if user.role == Role.COMMERCANT and getattr(user, 'fiche_commercant', None):
            fiche = user.fiche_commercant
            dus = solde_tickets(fiche, marche)
            ctx['solde'] = montant_solde(dus)
            ctx['tickets_dus'] = dus
            detail = tickets.filter(commercant=fiche)
            paiements = paiements.filter(commercant=fiche)
            ctx['detail_personnel'] = True
        labels = dict(StatutTicket.choices)
        nb_total = detail.count()
        ctx['nb_annules'] = tickets.filter(statut=StatutTicket.ANNULE).count()
        ctx['nb_paiements'] = Paiement.objects.filter(
            marche=marche, statut=Paiement.Statut.SUCCES, confirmed_at__date=jour
        ).count()
        ctx['taux'] = round(100 * ctx['nb_payes'] / ctx['nb_emis'], 1) if ctx['nb_emis'] else 0
        ctx['repartition'] = [
            {
                'code': row['statut'],
                'label': labels.get(row['statut'], row['statut']),
                'nb': row['nb'],
                'pct': round(100 * row['nb'] / nb_total) if nb_total else 0,
            }
            for row in detail.values('statut').annotate(nb=Count('id')).order_by('-nb')
        ]
        ctx['tickets_recents'] = detail.select_related('commercant', 'place').order_by('-id')[:8]
        ctx['paiements_recents'] = paiements.order_by('-created_at')[:8]
        return ctx

    def post(self, request, *args, **kwargs):
        marche_id = request.POST.get('marche_id')
        if marche_id:
            marche = marches_visibles(request.user).filter(pk=marche_id).first()
            if marche:
                request.session['marche_id'] = marche.pk
        return redirect('site_:dashboard')


class CommuneListView(RoleRequiredMixin, ListView):
    allowed_roles = {Role.ADMIN_GENERAL}
    model = Commune
    template_name = 'marches/commune_list.html'

    def get_queryset(self):
        return super().get_queryset().filter(suppression_demandee_le__isnull=True)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault('form', CommuneForm())
        if self.request.user.is_admin_general:
            ctx['suppressions'] = (
                Commune.objects.filter(suppression_demandee_le__isnull=False)
                .select_related('suppression_demandee_par')
            )
        return ctx

    def post(self, request, *args, **kwargs):
        form = CommuneForm(request.POST)
        if form.is_valid():
            self.object = form.save()
            audit(request.user, 'commune_creee', self.object)
            messages.success(request, 'Commune créée.')
            return redirect('marches:communes')
        self.object_list = self.get_queryset()
        ctx = self.get_context_data()
        ctx['form'] = form
        ctx['ouvrir_modal'] = True
        return self.render_to_response(ctx)


class CommuneCreateView(RoleRequiredMixin, CreateView):
    allowed_roles = {Role.ADMIN_GENERAL}
    model = Commune
    form_class = CommuneForm
    template_name = 'marches/form.html'
    extra_context = {'titre': 'Nouvelle commune'}
    success_url = reverse_lazy('marches:communes')

    def form_valid(self, form):
        response = super().form_valid(form)
        audit(self.request.user, 'commune_creee', self.object)
        messages.success(self.request, 'Commune créée.')
        return response


class CommuneUpdateView(RoleRequiredMixin, UpdateView):
    allowed_roles = {Role.ADMIN_GENERAL}
    model = Commune
    form_class = CommuneForm
    template_name = 'marches/form.html'
    extra_context = {'titre': 'Modifier la commune'}
    success_url = reverse_lazy('marches:communes')

    def get_queryset(self):
        return super().get_queryset().filter(suppression_demandee_le__isnull=True)


class CommuneSuppressionView(RoleRequiredMixin, View):
    allowed_roles = {Role.ADMIN_GENERAL}

    def post(self, request, pk):
        commune = get_object_or_404(Commune, pk=pk, suppression_demandee_le__isnull=True)
        commune.suppression_demandee_le = timezone.now()
        commune.suppression_demandee_par = request.user
        commune.save(update_fields=['suppression_demandee_le', 'suppression_demandee_par'])
        audit(request.user, 'commune_suppression_demandee', commune)
        messages.success(request, f'« {commune.nom} » est en attente de validation par l’admin général.')
        return redirect('marches:communes')


class CommuneValiderSuppressionView(RoleRequiredMixin, View):
    allowed_roles = {Role.ADMIN_GENERAL}

    def post(self, request, pk):
        commune = get_object_or_404(Commune, pk=pk, suppression_demandee_le__isnull=False)
        nom = commune.nom
        try:
            commune.delete()
        except ProtectedError:
            messages.error(
                request,
                f'« {nom} » a encore des marchés ou des utilisateurs. Récupérez-la, ou retirez ces liens avant de valider.',
            )
            return redirect('marches:communes')
        audit(request.user, 'commune_supprimee', commune, nom=nom)
        messages.success(request, f'« {nom} » a été supprimée.')
        return redirect('marches:communes')


class CommuneRecupererView(RoleRequiredMixin, View):
    allowed_roles = {Role.ADMIN_GENERAL}

    def post(self, request, pk):
        commune = get_object_or_404(Commune, pk=pk, suppression_demandee_le__isnull=False)
        commune.suppression_demandee_le = None
        commune.suppression_demandee_par = None
        commune.save(update_fields=['suppression_demandee_le', 'suppression_demandee_par'])
        audit(request.user, 'commune_recuperee', commune)
        messages.success(request, f'« {commune.nom} » a été récupérée.')
        return redirect('marches:communes')


class MarcheListView(RoleRequiredMixin, ListView):
    allowed_roles = {Role.ADMIN_GENERAL, Role.ADMIN_COMMUNE}
    model = Marche
    template_name = 'marches/marche_list.html'

    def get_queryset(self):
        return marches_geres(self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault('form', MarcheForm(editor=self.request.user))
        if self.request.user.is_admin_general:
            ctx['suppressions'] = (
                Marche.objects.filter(suppression_demandee_le__isnull=False)
                .select_related('commune', 'suppression_demandee_par')
            )
        return ctx

    def post(self, request, *args, **kwargs):
        form = MarcheForm(request.POST, editor=request.user)
        if form.is_valid():
            self.object = form.save()
            PenaliteParametre.objects.get_or_create(marche=self.object)
            audit(request.user, 'marche_cree', self.object)
            messages.success(request, 'Marché créé.')
            return redirect('marches:marches')
        self.object_list = self.get_queryset()
        ctx = self.get_context_data()
        ctx['form'] = form
        ctx['ouvrir_modal'] = True
        return self.render_to_response(ctx)


class MarcheCreateView(RoleRequiredMixin, CreateView):
    allowed_roles = {Role.ADMIN_GENERAL, Role.ADMIN_COMMUNE}
    model = Marche
    form_class = MarcheForm
    template_name = 'marches/form.html'
    extra_context = {'titre': 'Nouveau marché'}
    success_url = reverse_lazy('marches:marches')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['editor'] = self.request.user
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        PenaliteParametre.objects.get_or_create(marche=self.object)
        audit(self.request.user, 'marche_cree', self.object)
        messages.success(self.request, 'Marché créé.')
        return response


class MarcheUpdateView(RoleRequiredMixin, UpdateView):
    allowed_roles = {Role.ADMIN_GENERAL, Role.ADMIN_COMMUNE}
    model = Marche
    form_class = MarcheForm
    template_name = 'marches/form.html'
    extra_context = {'titre': 'Modifier le marché'}
    success_url = reverse_lazy('marches:marches')

    def get_queryset(self):
        return marches_geres(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['editor'] = self.request.user
        return kwargs


class MarcheSuppressionView(RoleRequiredMixin, View):
    allowed_roles = {Role.ADMIN_GENERAL, Role.ADMIN_COMMUNE}

    def post(self, request, pk):
        marche = get_object_or_404(marches_geres(request.user), pk=pk)
        marche.suppression_demandee_le = timezone.now()
        marche.suppression_demandee_par = request.user
        marche.save(update_fields=['suppression_demandee_le', 'suppression_demandee_par'])
        audit(request.user, 'marche_suppression_demandee', marche)
        messages.success(request, f'« {marche.nom} » est en attente de validation par l’admin général.')
        return redirect('marches:marches')


class MarcheValiderSuppressionView(RoleRequiredMixin, View):
    allowed_roles = {Role.ADMIN_GENERAL}

    def post(self, request, pk):
        marche = get_object_or_404(Marche, pk=pk, suppression_demandee_le__isnull=False)
        nom = marche.nom
        try:
            marche.delete()
        except ProtectedError:
            messages.error(
                request,
                f'« {nom} » a encore des places, des commerçants, des tickets ou des utilisateurs. Récupérez-le, ou retirez ces liens avant de valider.',
            )
            return redirect('marches:marches')
        audit(request.user, 'marche_supprime', marche, nom=nom)
        messages.success(request, f'« {nom} » a été supprimé.')
        return redirect('marches:marches')


class MarcheRecupererView(RoleRequiredMixin, View):
    allowed_roles = {Role.ADMIN_GENERAL}

    def post(self, request, pk):
        marche = get_object_or_404(Marche, pk=pk, suppression_demandee_le__isnull=False)
        marche.suppression_demandee_le = None
        marche.suppression_demandee_par = None
        marche.save(update_fields=['suppression_demandee_le', 'suppression_demandee_par'])
        audit(request.user, 'marche_recupere', marche)
        messages.success(request, f'« {marche.nom} » a été récupéré.')
        return redirect('marches:marches')


class UserListView(RoleRequiredMixin, ListView):
    allowed_roles = {Role.ADMIN_GENERAL, Role.ADMIN_COMMUNE}
    model = CustomUser
    template_name = 'accounts/user_list.html'

    def get_queryset(self):
        qs = CustomUser.objects.select_related('commune', 'marche')
        user = self.request.user
        if user.is_admin_general:
            return qs
        return qs.filter(commune=user.commune).exclude(role=Role.ADMIN_GENERAL)


class UserCreateView(RoleRequiredMixin, CreateView):
    allowed_roles = {Role.ADMIN_GENERAL, Role.ADMIN_COMMUNE}
    model = CustomUser
    form_class = UserForm
    template_name = 'accounts/form.html'
    extra_context = {'titre': 'Nouvel utilisateur'}
    success_url = reverse_lazy('site_:utilisateurs')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['editor'] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, 'Utilisateur créé.')
        return super().form_valid(form)


class UserUpdateView(RoleRequiredMixin, UpdateView):
    allowed_roles = {Role.ADMIN_GENERAL, Role.ADMIN_COMMUNE}
    model = CustomUser
    form_class = UserForm
    template_name = 'accounts/form.html'
    extra_context = {'titre': 'Modifier l’utilisateur'}
    success_url = reverse_lazy('site_:utilisateurs')

    def get_queryset(self):
        return UserListView.get_queryset(self)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['editor'] = self.request.user
        return kwargs


class TypePlaceListView(RoleRequiredMixin, ListView):
    allowed_roles = {Role.ADMIN_GENERAL, Role.ADMIN_COMMUNE, Role.REGISSEUR}
    model = TypePlace
    template_name = 'marches/typeplace_list.html'

    def get_queryset(self):
        marche = marche_courant(self.request)
        return TypePlace.objects.filter(marche=marche) if marche else TypePlace.objects.none()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['marche'] = marche_courant(self.request)
        ctx.setdefault('form', TypePlaceForm())
        return ctx

    def post(self, request, *args, **kwargs):
        form = TypePlaceForm(request.POST)
        if form.is_valid():
            form.instance.marche = marche_courant(request)
            if form.instance.marche_id:
                form.save()
                messages.success(request, 'Type de place enregistré.')
                return redirect('marches:types_place')
            form.add_error(None, 'Choisissez un marché avant d’enregistrer un type de place.')
        self.object_list = self.get_queryset()
        ctx = self.get_context_data()
        ctx['form'] = form
        ctx['ouvrir_modal'] = True
        return self.render_to_response(ctx)


class TypePlaceCreateView(RoleRequiredMixin, CreateView):
    allowed_roles = {Role.ADMIN_GENERAL, Role.ADMIN_COMMUNE, Role.REGISSEUR}
    model = TypePlace
    form_class = TypePlaceForm
    template_name = 'marches/form.html'
    extra_context = {'titre': 'Type de place'}
    success_url = reverse_lazy('marches:types_place')

    def form_valid(self, form):
        form.instance.marche = marche_courant(self.request)
        return super().form_valid(form)


class TarifListView(RoleRequiredMixin, ListView):
    allowed_roles = {Role.ADMIN_GENERAL, Role.ADMIN_COMMUNE, Role.REGISSEUR}
    model = Tarif
    template_name = 'marches/tarif_list.html'

    def get_queryset(self):
        marche = marche_courant(self.request)
        return Tarif.objects.filter(type_place__marche=marche).select_related('type_place') if marche else Tarif.objects.none()

    def _form(self, data=None):
        form = TarifForm(data)
        marche = marche_courant(self.request)
        form.fields['type_place'].queryset = marche.types_place.all() if marche else TypePlace.objects.none()
        return form

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['marche'] = marche_courant(self.request)
        ctx.setdefault('form', self._form())
        return ctx

    def post(self, request, *args, **kwargs):
        form = self._form(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Tarif enregistré.')
            return redirect('marches:tarifs')
        self.object_list = self.get_queryset()
        ctx = self.get_context_data()
        ctx['form'] = form
        ctx['ouvrir_modal'] = True
        return self.render_to_response(ctx)


class TarifCreateView(RoleRequiredMixin, CreateView):
    allowed_roles = {Role.ADMIN_GENERAL, Role.ADMIN_COMMUNE, Role.REGISSEUR}
    model = Tarif
    form_class = TarifForm
    template_name = 'marches/form.html'
    extra_context = {'titre': 'Nouveau tarif'}
    success_url = reverse_lazy('marches:tarifs')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        marche = marche_courant(self.request)
        if marche:
            form.fields['type_place'].queryset = marche.types_place.all()
        return form


class PenaliteUpdateView(RoleRequiredMixin, UpdateView):
    allowed_roles = ROLES_PENALITE
    model = PenaliteParametre
    form_class = PenaliteForm
    template_name = 'marches/form.html'
    extra_context = {'titre': 'Paramètre de pénalité'}
    success_url = reverse_lazy('site_:dashboard')

    def get_object(self, queryset=None):
        marche = marche_courant(self.request)
        obj, _ = PenaliteParametre.objects.get_or_create(marche=marche)
        return obj


class CommercantListView(RoleRequiredMixin, ListView):
    allowed_roles = ROLES_COLLECTE | ROLES_MAIRIE
    model = Commercant
    template_name = 'recensement/commercant_list.html'

    def get_queryset(self):
        marche = marche_courant(self.request)
        qs = Commercant.objects.filter(marche=marche) if marche else Commercant.objects.none()
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(Q(nom__icontains=q) | Q(telephone__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['marche'] = marche_courant(self.request)
        ctx['peut_creer'] = self.request.user.is_admin_general or self.request.user.role in ROLES_COLLECTE
        ctx.setdefault('form', CommercantForm())
        return ctx

    def post(self, request, *args, **kwargs):
        if not (request.user.is_admin_general or request.user.role in ROLES_COLLECTE):
            raise PermissionDenied
        form = CommercantForm(request.POST, request.FILES)
        marche = marche_courant(request)
        if form.is_valid() and marche:
            form.instance.marche = marche
            form.instance.created_by = request.user
            form.save()
            messages.success(request, 'Commerçant recensé.')
            return redirect('recensement:commercants')
        if form.is_valid() and not marche:
            form.add_error(None, 'Choisissez un marché avant de recenser un commerçant.')
        self.object_list = self.get_queryset()
        ctx = self.get_context_data()
        ctx['form'] = form
        ctx['ouvrir_modal'] = True
        return self.render_to_response(ctx)


class CommercantCreateView(RoleRequiredMixin, CreateView):
    allowed_roles = ROLES_COLLECTE
    model = Commercant
    form_class = CommercantForm
    template_name = 'recensement/form.html'
    extra_context = {'titre': 'Nouveau commerçant'}
    success_url = reverse_lazy('recensement:commercants')

    def form_valid(self, form):
        form.instance.marche = marche_courant(self.request)
        form.instance.created_by = self.request.user
        messages.success(self.request, 'Commerçant recensé.')
        return super().form_valid(form)


class PlaceListView(RoleRequiredMixin, ListView):
    allowed_roles = ROLES_COLLECTE | ROLES_MAIRIE
    model = Place
    template_name = 'recensement/place_list.html'

    def get_queryset(self):
        marche = marche_courant(self.request)
        return Place.objects.filter(marche=marche).select_related('commercant', 'type_place') if marche else Place.objects.none()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        marche = marche_courant(self.request)
        ctx['marche'] = marche
        ctx['peut_creer'] = self.request.user.is_admin_general or self.request.user.role in ROLES_COLLECTE
        ctx.setdefault('form', PlaceForm(marche=marche))
        return ctx

    def post(self, request, *args, **kwargs):
        if not (request.user.is_admin_general or request.user.role in ROLES_COLLECTE):
            raise PermissionDenied
        marche = marche_courant(request)
        form = PlaceForm(request.POST, request.FILES, marche=marche)
        if form.is_valid() and marche:
            form.instance.marche = marche
            form.instance.created_by = request.user
            self.object = form.save()
            ticket, created = emettre_ticket(self.object, emetteur=request.user)
            if created:
                messages.success(request, f'Place enregistrée et ticket {ticket.numero} émis.')
            else:
                messages.info(request, f'Place enregistrée. Ticket du jour déjà existant : {ticket.numero}.')
            return redirect('recensement:places')
        if form.is_valid() and not marche:
            form.add_error(None, 'Choisissez un marché avant d’enregistrer une place.')
        self.object_list = self.get_queryset()
        ctx = self.get_context_data()
        ctx['form'] = form
        ctx['ouvrir_modal'] = True
        return self.render_to_response(ctx)


class PlaceCreateView(RoleRequiredMixin, CreateView):
    allowed_roles = ROLES_COLLECTE
    model = Place
    form_class = PlaceForm
    template_name = 'recensement/form.html'
    extra_context = {'titre': 'Nouvelle place / déambulant'}
    success_url = reverse_lazy('recensement:places')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['marche'] = marche_courant(self.request)
        return kwargs

    def form_valid(self, form):
        marche = marche_courant(self.request)
        form.instance.marche = marche
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        ticket, created = emettre_ticket(self.object, emetteur=self.request.user)
        if created:
            messages.success(self.request, f'Place enregistrée et ticket {ticket.numero} émis.')
        else:
            messages.info(self.request, f'Place enregistrée. Ticket du jour déjà existant : {ticket.numero}.')
        return response


class TicketListView(RoleRequiredMixin, ListView):
    allowed_roles = ROLES_COLLECTE | ROLES_MAIRIE | ROLES_CONTROLE | {Role.COMMERCANT}
    model = Ticket
    template_name = 'tickets/ticket_list.html'
    paginate_by = 50

    def get_queryset(self):
        user = self.request.user
        marche = marche_courant(self.request)
        qs = Ticket.objects.select_related('commercant', 'place', 'marche')
        if user.role == Role.COMMERCANT and getattr(user, 'fiche_commercant', None):
            return qs.filter(commercant=user.fiche_commercant)
        if marche:
            qs = qs.filter(marche=marche)
        else:
            qs = scoped_qs(qs, user)
        statut = self.request.GET.get('statut')
        if statut:
            qs = qs.filter(statut=statut)
        jour = self.request.GET.get('jour')
        if jour:
            qs = qs.filter(date_validite=jour)
        elif statut != 'impaye':
            qs = qs.filter(date_validite=timezone.localdate())
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['statuts'] = StatutTicket.choices
        ctx['filtre_statut'] = self.request.GET.get('statut', '')
        ctx['marche'] = marche_courant(self.request)
        return ctx


class TicketDetailView(RoleRequiredMixin, TemplateView):
    allowed_roles = ROLES_COLLECTE | ROLES_MAIRIE | ROLES_CONTROLE | {Role.COMMERCANT}
    template_name = 'tickets/ticket_detail.html'

    def get_ticket(self):
        ticket = Ticket.objects.select_related('commercant', 'place', 'marche').get(pk=self.kwargs['pk'])
        user = self.request.user
        if user.role == Role.COMMERCANT and getattr(user, 'fiche_commercant', None):
            if ticket.commercant_id != user.fiche_commercant.id:
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied
        elif ticket.marche not in marches_visibles(user):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
        return ticket

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['ticket'] = self.get_ticket()
        ctx['annulation_form'] = AnnulationForm()
        return ctx


class TicketAnnulerView(RoleRequiredMixin, TemplateView):
    allowed_roles = ROLES_COLLECTE | ROLES_CLOTURE
    http_method_names = ['post']

    def post(self, request, pk):
        ticket = Ticket.objects.get(pk=pk)
        form = AnnulationForm(request.POST)
        if form.is_valid():
            try:
                annuler_ticket(ticket, request.user, form.cleaned_data['motif'])
                messages.success(request, 'Ticket annulé.')
            except Exception as exc:
                messages.error(request, str(exc))
        return redirect('tickets:ticket_detail', pk=pk)


class GenererTicketsView(RoleRequiredMixin, TemplateView):
    allowed_roles = ROLES_COLLECTE | ROLES_CLOTURE
    http_method_names = ['post']

    def post(self, request):
        marche = marche_courant(request)
        crees = generer_tickets_du_jour(marche, emetteur=request.user)
        messages.success(request, f'{len(crees)} ticket(s) généré(s) pour aujourd’hui.')
        return redirect('tickets:tickets')


class ImpayesListView(RoleRequiredMixin, ListView):
    allowed_roles = ROLES_COLLECTE | ROLES_MAIRIE | ROLES_CONTROLE
    model = Ticket
    template_name = 'tickets/impayes.html'

    def get_queryset(self):
        marche = marche_courant(self.request)
        return Ticket.objects.filter(marche=marche, statut=StatutTicket.IMPAYE).select_related('commercant', 'place')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['marche'] = marche_courant(self.request)
        return ctx


class PayerView(RoleRequiredMixin, TemplateView):
    allowed_roles = {Role.COMMERCANT, Role.COLLECTEUR, Role.ADMIN_GENERAL, Role.ADMIN_COMMUNE}
    template_name = 'tickets/payer.html'

    def _commercant(self):
        user = self.request.user
        cid = self.request.GET.get('commercant') or self.request.POST.get('commercant')
        if user.role == Role.COMMERCANT:
            return user.fiche_commercant
        if cid:
            return Commercant.objects.get(pk=cid)
        return None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        commercant = self._commercant()
        marche = marche_courant(self.request)
        ctx['commercant'] = commercant
        ctx['commercants'] = Commercant.objects.filter(marche=marche, actif=True) if marche else []
        if commercant:
            dus = solde_tickets(commercant, commercant.marche)
            ctx['tickets_dus'] = dus
            ctx['solde'] = montant_solde(dus)
        return ctx

    def post(self, request, *args, **kwargs):
        commercant = self._commercant()
        if not commercant:
            messages.error(request, 'Choisissez un commerçant.')
            return redirect('tickets:payer')
        try:
            paiement = initier_paiement(commercant, initiateur=request.user, marche=commercant.marche)
        except Exception as exc:
            messages.error(request, str(exc))
            return redirect('tickets:payer')
        return redirect('tickets:paiement_mock', token=paiement.mock_token)


class PaiementMockView(LoginRequiredMixin, TemplateView):
    template_name = 'tickets/paiement_mock.html'

    def get_paiement(self):
        return Paiement.objects.select_related('commercant', 'marche').prefetch_related('lignes__ticket').get(
            mock_token=self.kwargs['token']
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['paiement'] = self.get_paiement()
        return ctx

    def post(self, request, token):
        paiement = Paiement.objects.get(mock_token=token)
        action = request.POST.get('action')
        mapping = {
            'confirmer': Paiement.Statut.SUCCES,
            'refuser': Paiement.Statut.ECHEC,
            'timeout': Paiement.Statut.TIMEOUT,
        }
        try:
            callback_paiement(paiement, mapping.get(action, Paiement.Statut.ECHEC))
        except Exception as exc:
            messages.error(request, str(exc))
        paiement.refresh_from_db()
        if paiement.statut == Paiement.Statut.SUCCES:
            messages.success(request, 'Paiement Orange Money confirmé.')
            return redirect('tickets:recu', token=token)
        messages.warning(request, 'Paiement non abouti. Vous pouvez réessayer.')
        return redirect('tickets:payer')


class RecuView(LoginRequiredMixin, TemplateView):
    template_name = 'tickets/recu.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['paiement'] = Paiement.objects.select_related('commercant', 'marche').prefetch_related(
            'lignes__ticket'
        ).get(mock_token=self.kwargs['token'])
        return ctx


class ScanView(RoleRequiredMixin, TemplateView):
    allowed_roles = ROLES_CONTROLE
    template_name = 'tickets/scan.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['form'] = ScanForm()
        return ctx

    def post(self, request):
        form = ScanForm(request.POST)
        resultat = None
        if form.is_valid():
            payload = form.cleaned_data['payload'].strip()
            if '.' not in payload:
                ticket = Ticket.objects.filter(numero=payload).first()
                payload = ticket.qr_payload if ticket else payload
            resultat = verifier_qr(payload, controleur=request.user)
        return self.render_to_response({'form': form, 'resultat': resultat})


class ClotureView(RoleRequiredMixin, TemplateView):
    allowed_roles = ROLES_CLOTURE
    template_name = 'tickets/cloture.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        marche = marche_courant(self.request)
        jour = timezone.localdate()
        ctx['marche'] = marche
        ctx['jour'] = jour
        ctx['cloture'] = ClotureJournee.objects.filter(marche=marche, date=jour).first() if marche else None
        ctx['historique'] = ClotureJournee.objects.filter(marche=marche)[:14] if marche else []
        return ctx

    def post(self, request):
        marche = marche_courant(request)
        try:
            cloture = cloturer_journee(marche, auteur=request.user)
            messages.success(request, f'Journée clôturée : {cloture.tickets_impayes} impayé(s), pénalités {cloture.penalites_emises} GNF.')
        except Exception as exc:
            messages.error(request, str(exc))
        return redirect('tickets:cloture')


class PenaliteAnnulerView(RoleRequiredMixin, TemplateView):
    allowed_roles = ROLES_PENALITE
    http_method_names = ['post']

    def post(self, request, pk):
        ticket = Ticket.objects.get(pk=pk)
        form = AnnulationForm(request.POST)
        if form.is_valid():
            try:
                annuler_penalite(ticket, request.user, form.cleaned_data['motif'])
                messages.success(request, 'Pénalité annulée.')
            except Exception as exc:
                messages.error(request, str(exc))
        return redirect('tickets:ticket_detail', pk=pk)


class RapportView(RoleRequiredMixin, TemplateView):
    allowed_roles = ROLES_BACKOFFICE
    template_name = 'tickets/rapport.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        marche = marche_courant(self.request)
        jour = timezone.localdate()
        ctx['marche'] = marche
        ctx['jour'] = jour
        if not marche:
            return ctx
        tickets = Ticket.objects.filter(marche=marche, date_validite=jour)
        payes = tickets.filter(statut__in=[StatutTicket.PAYE, StatutTicket.CONTROLE])
        ctx['nb_emis'] = tickets.exclude(statut=StatutTicket.ANNULE).count()
        ctx['nb_payes'] = payes.count()
        ctx['nb_impayes'] = Ticket.objects.filter(marche=marche, statut=StatutTicket.IMPAYE).count()
        ctx['nb_regularises'] = Ticket.objects.filter(
            marche=marche, statut=StatutTicket.REGULARISE, lignes_paiement__paiement__confirmed_at__date=jour
        ).distinct().count()
        ctx['montant_om'] = (
            Paiement.objects.filter(marche=marche, statut=Paiement.Statut.SUCCES, confirmed_at__date=jour).aggregate(
                s=Sum('montant')
            )['s']
            or 0
        )
        ctx['penalites_emises'] = (
            Ticket.objects.filter(marche=marche, date_validite=jour, statut=StatutTicket.IMPAYE).aggregate(
                s=Sum('montant_penalite')
            )['s']
            or 0
        )
        ctx['par_collecteur'] = (
            tickets.exclude(statut=StatutTicket.ANNULE)
            .values('emetteur__username')
            .annotate(nb=Count('id'), montant=Sum('montant'))
        )
        ctx['taux'] = round(100 * ctx['nb_payes'] / ctx['nb_emis'], 1) if ctx['nb_emis'] else 0
        ctx['clotures'] = ClotureJournee.objects.filter(marche=marche)[:10]
        return ctx


class TicketQrView(LoginRequiredMixin, TemplateView):
    def get(self, request, pk):
        ticket = get_object_or_404(Ticket, pk=pk)
        img = qrcode.make(ticket.qr_payload)
        buf = BytesIO()
        img.save(buf, format='PNG')
        return HttpResponse(buf.getvalue(), content_type='image/png')


class AuditListView(RoleRequiredMixin, ListView):
    allowed_roles = ROLES_BACKOFFICE
    model = JournalAudit
    template_name = 'tickets/audit.html'
    paginate_by = 80

    def get_queryset(self):
        qs = JournalAudit.objects.select_related('user')
        user = self.request.user
        if not user.is_admin_general and user.commune_id:
            qs = qs.filter(Q(user__commune=user.commune) | Q(user__isnull=True))
        return qs


class RechercheView(LoginRequiredMixin, TemplateView):
    template_name = 'site_/recherche.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        q = (self.request.GET.get('q') or '').strip()
        ctx['q'] = q
        ctx['trop_court'] = bool(q) and len(q) < 2
        ctx['groupes'] = [] if ctx['trop_court'] or not q else resultats_recherche(self.request.user, q)
        return ctx


def _ajouter(groupes, titre, lignes):
    if lignes:
        groupes.append({'titre': titre, 'lignes': lignes})


def resultats_recherche(user, q):
    groupes = []
    if user.is_admin_general:
        communes = Commune.objects.filter(
            suppression_demandee_le__isnull=True,
        ).filter(Q(nom__icontains=q) | Q(code__icontains=q))[:8]
        _ajouter(groupes, 'Communes', [
            {
                'label': commune.nom,
                'detail': commune.code,
                'url': reverse('marches:commune_update', args=[commune.pk]),
            }
            for commune in communes
        ])

    marches = marches_visibles(user).filter(
        Q(nom__icontains=q) | Q(adresse__icontains=q) | Q(commune__nom__icontains=q)
    )[:8]
    marche_url = user.is_admin_general or user.role == Role.ADMIN_COMMUNE
    _ajouter(groupes, 'Marchés', [
        {
            'label': marche.nom,
            'detail': str(marche.commune),
            'url': reverse('marches:marche_update', args=[marche.pk]) if marche_url else '',
        }
        for marche in marches
    ])

    if user.is_admin_general or user.role == Role.ADMIN_COMMUNE:
        utilisateurs = CustomUser.objects.select_related('commune', 'marche')
        if not user.is_admin_general:
            utilisateurs = utilisateurs.filter(commune=user.commune).exclude(role=Role.ADMIN_GENERAL)
        utilisateurs = utilisateurs.filter(
            Q(username__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(telephone__icontains=q)
        )[:8]
        _ajouter(groupes, 'Utilisateurs', [
            {
                'label': personne.get_full_name() or personne.username,
                'detail': f'{personne.get_role_display()} · {personne.telephone}',
                'url': reverse('site_:user_update', args=[personne.pk]),
            }
            for personne in utilisateurs
        ])

    commercants = Commercant.objects.select_related('marche')
    if user.role == Role.COMMERCANT:
        commercants = commercants.filter(user=user)
    else:
        commercants = scoped_qs(commercants, user)
    commercants = commercants.filter(Q(nom__icontains=q) | Q(telephone__icontains=q))[:8]
    peut_payer = user.is_admin_general or user.role in {Role.ADMIN_COMMUNE, Role.COLLECTEUR, Role.COMMERCANT}
    _ajouter(groupes, 'Commerçants', [
        {
            'label': commercant.nom,
            'detail': f'{commercant.telephone} · {commercant.marche.nom}',
            'url': f"{reverse('tickets:payer')}?commercant={commercant.pk}" if peut_payer else '',
        }
        for commercant in commercants
    ])

    places = Place.objects.select_related('commercant', 'type_place', 'marche')
    if user.role == Role.COMMERCANT:
        places = places.filter(commercant__user=user)
    else:
        places = scoped_qs(places, user)
    places = places.filter(
        Q(code__icontains=q) | Q(commercant__nom__icontains=q) | Q(commercant__telephone__icontains=q)
    )[:8]
    _ajouter(groupes, 'Places', [
        {
            'label': place.code,
            'detail': f'{place.type_place.nom} · {place.commercant.nom}',
            'url': '',
        }
        for place in places
    ])

    tickets = Ticket.objects.select_related('commercant', 'place', 'marche')
    if user.role == Role.COMMERCANT:
        fiche = getattr(user, 'fiche_commercant', None)
        tickets = tickets.filter(commercant=fiche) if fiche else tickets.none()
    else:
        tickets = scoped_qs(tickets, user)
    tickets = tickets.filter(
        Q(numero__icontains=q)
        | Q(commercant__nom__icontains=q)
        | Q(commercant__telephone__icontains=q)
        | Q(place__code__icontains=q)
    )[:8]
    _ajouter(groupes, 'Tickets', [
        {
            'label': ticket.numero,
            'detail': f'{ticket.commercant.nom} · {ticket.get_statut_display()}',
            'url': reverse('tickets:ticket_detail', args=[ticket.pk]),
        }
        for ticket in tickets
    ])
    return groupes
