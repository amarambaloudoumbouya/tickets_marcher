from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import PasswordChangeView
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import FormView, UpdateView

from accounts.forms import MotDePasseForm, ProfilForm, UnlockForm
from accounts.models import CustomUser


class ProfilView(LoginRequiredMixin, UpdateView):
    model = CustomUser
    form_class = ProfilForm
    template_name = 'accounts/profil.html'
    success_url = reverse_lazy('accounts:profil')

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, 'Profil enregistré.')
        return super().form_valid(form)


class MotDePasseView(LoginRequiredMixin, PasswordChangeView):
    form_class = MotDePasseForm
    template_name = 'accounts/mot_de_passe.html'
    success_url = reverse_lazy('accounts:profil')

    def form_valid(self, form):
        messages.success(self.request, 'Mot de passe modifié.')
        return super().form_valid(form)


class LockView(LoginRequiredMixin, View):
    def post(self, request):
        request.session['compte_verrouille'] = True
        return redirect('accounts:unlock')


class UnlockView(LoginRequiredMixin, FormView):
    form_class = UnlockForm
    template_name = 'registration/unlock.html'
    success_url = reverse_lazy('site_:dashboard')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        self.request.session['compte_verrouille'] = False
        return super().form_valid(form)
