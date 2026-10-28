from django.db.models import Q
from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm

from accounts.models import ROLES_COMMUNE, ROLES_MARCHE, ROLES_MEMBRES_MARCHE, CustomUser, Role, roles_creables
from marches.models import Commune, Marche


class LoginForm(AuthenticationForm):
    username = forms.CharField(label='Identifiant', widget=forms.TextInput(attrs={'autofocus': True}))
    password = forms.CharField(label='Mot de passe', widget=forms.PasswordInput)


class UserForm(forms.ModelForm):
    password1 = forms.CharField(label='Mot de passe', widget=forms.PasswordInput, required=False)
    password2 = forms.CharField(label='Confirmation', widget=forms.PasswordInput, required=False)

    class Meta:
        model = CustomUser
        fields = ['username', 'first_name', 'last_name', 'telephone', 'email', 'role', 'commune', 'marche', 'numero_om', 'is_active']

    def __init__(self, *args, editor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.editor = editor
        visibles = Commune.objects.filter(suppression_demandee_le__isnull=True)
        if self.instance.commune_id:
            visibles = Commune.objects.filter(
                Q(suppression_demandee_le__isnull=True) | Q(pk=self.instance.commune_id)
            )
        self.fields['commune'].queryset = visibles
        if not self.instance.pk:
            self.fields['password1'].required = True
            self.fields['password2'].required = True
        self.fields['numero_om'].required = False
        self.fields['numero_om'].label = 'Numéro Orange Money'
        self.fields['numero_om'].help_text = (
            'Octroyé par la commune au contrôleur. La demande de retrait y est envoyée '
            'quand il paie pour un commerçant.'
        )
        if not editor:
            return
        autorises = roles_creables(editor)
        self.fields['role'].choices = [(role.value, role.label) for role in Role if role in autorises]
        if editor.is_admin_general:
            marches = Marche.objects.filter(suppression_demandee_le__isnull=True)
            if self.instance.marche_id:
                marches = Marche.objects.filter(
                    Q(suppression_demandee_le__isnull=True) | Q(pk=self.instance.marche_id)
                )
            self.fields['marche'].queryset = marches
            self.fields['commune'].required = False
            self.fields['marche'].required = False
            return
        if editor.role == Role.ADMIN_COMMUNE:
            self.fields['commune'].queryset = Commune.objects.filter(pk=editor.commune_id)
            self.fields['commune'].initial = editor.commune_id
            self.fields['commune'].widget = forms.HiddenInput()
            marches = Marche.objects.filter(
                commune_id=editor.commune_id,
                suppression_demandee_le__isnull=True,
            )
            if self.instance.marche_id:
                marches = Marche.objects.filter(
                    Q(pk__in=marches.values('pk')) | Q(pk=self.instance.marche_id)
                )
            self.fields['marche'].queryset = marches
            self.fields['marche'].required = False
            return
        if editor.role == Role.ADMIN_MARCHE:
            self.fields['commune'].queryset = Commune.objects.filter(pk=editor.commune_id)
            self.fields['commune'].initial = editor.commune_id
            self.fields['commune'].widget = forms.HiddenInput()
            self.fields['marche'].queryset = Marche.objects.filter(pk=editor.marche_id)
            self.fields['marche'].initial = editor.marche_id
            self.fields['marche'].widget = forms.HiddenInput()

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get('password1'), cleaned.get('password2')
        if p1 or p2:
            if p1 != p2:
                self.add_error('password2', 'Les mots de passe ne correspondent pas.')
        editor = self.editor
        role = cleaned.get('role')
        if not editor or not role:
            return cleaned
        if role not in roles_creables(editor):
            self.add_error('role', 'Vous ne pouvez pas attribuer ce rôle.')
            return cleaned
        if role == Role.CONTROLEUR and not (cleaned.get('numero_om') or '').strip():
            self.add_error('numero_om', 'Indiquez le numéro Orange Money octroyé par la commune.')
        elif role != Role.CONTROLEUR:
            cleaned['numero_om'] = ''
        if editor.is_admin_general:
            if role == Role.ADMIN_GENERAL:
                cleaned['commune'] = None
                cleaned['marche'] = None
            elif role in ROLES_COMMUNE:
                cleaned['marche'] = None
                if not cleaned.get('commune'):
                    self.add_error('commune', 'Une commune est obligatoire pour ce rôle.')
            elif role in ROLES_MARCHE:
                if not cleaned.get('marche'):
                    self.add_error('marche', 'Un marché est obligatoire pour ce rôle.')
                else:
                    marche = cleaned['marche']
                    commune = cleaned.get('commune')
                    if commune and marche.commune_id != commune.pk:
                        self.add_error('marche', 'Le marché doit appartenir à la commune choisie.')
                    elif not commune:
                        cleaned['commune'] = marche.commune
            return cleaned
        if editor.role == Role.ADMIN_COMMUNE:
            self.errors.pop('commune', None)
            cleaned['commune'] = editor.commune
            if role == Role.MAIRE:
                self.errors.pop('marche', None)
                cleaned['marche'] = None
            elif not cleaned.get('marche'):
                self.add_error('marche', 'Un marché est obligatoire pour ce rôle.')
            elif cleaned['marche'].commune_id != editor.commune_id:
                self.add_error('marche', 'Le marché doit appartenir à votre commune.')
            return cleaned
        if editor.role == Role.ADMIN_MARCHE:
            if role not in ROLES_MEMBRES_MARCHE:
                self.add_error('role', 'Vous ne pouvez pas attribuer ce rôle.')
            self.errors.pop('commune', None)
            self.errors.pop('marche', None)
            cleaned['commune'] = editor.commune
            cleaned['marche'] = editor.marche
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        pwd = self.cleaned_data.get('password1')
        if pwd:
            user.set_password(pwd)
        editor = self.editor
        if editor and not editor.is_admin_general and editor.role == Role.ADMIN_COMMUNE:
            user.commune = editor.commune
            if user.role == Role.MAIRE:
                user.marche = None
        elif editor and not editor.is_admin_general and editor.role == Role.ADMIN_MARCHE:
            user.commune = editor.commune
            user.marche = editor.marche
        if user.role == Role.ADMIN_GENERAL:
            user.commune = None
            user.marche = None
        elif user.role in {Role.ADMIN_COMMUNE, Role.MAIRE}:
            user.marche = None
        if user.role != Role.CONTROLEUR:
            user.numero_om = ''
        if user.marche_id and not user.commune_id:
            user.commune_id = user.marche.commune_id
        if commit:
            user.save()
        return user


class ProfilForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'email', 'telephone']
        labels = {
            'first_name': 'Prénom',
            'last_name': 'Nom',
            'email': 'E-mail',
            'telephone': 'Téléphone',
        }


class MotDePasseForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['old_password'].label = 'Mot de passe actuel'
        self.fields['new_password1'].label = 'Nouveau mot de passe'
        self.fields['new_password2'].label = 'Confirmation'


class UnlockForm(forms.Form):
    password = forms.CharField(
        label='Mot de passe',
        widget=forms.PasswordInput(attrs={'autofocus': True}),
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self):
        password = self.cleaned_data['password']
        if not self.user.check_password(password):
            raise forms.ValidationError('Mot de passe incorrect.')
        return password
