from django.db.models import Q
from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm

from accounts.models import CustomUser, Role
from marches.models import Commune, Marche


class LoginForm(AuthenticationForm):
    username = forms.CharField(label='Identifiant', widget=forms.TextInput(attrs={'autofocus': True}))
    password = forms.CharField(label='Mot de passe', widget=forms.PasswordInput)


class UserForm(forms.ModelForm):
    password1 = forms.CharField(label='Mot de passe', widget=forms.PasswordInput, required=False)
    password2 = forms.CharField(label='Confirmation', widget=forms.PasswordInput, required=False)

    class Meta:
        model = CustomUser
        fields = ['username', 'first_name', 'last_name', 'telephone', 'email', 'role', 'commune', 'marche', 'is_active']

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
        if editor and not editor.is_admin_general:
            self.fields['commune'].queryset = Commune.objects.filter(pk=editor.commune_id)
            self.fields['marche'].queryset = Marche.objects.filter(commune_id=editor.commune_id)
            self.fields['role'].choices = [
                (r.value, r.label)
                for r in Role
                if r not in {Role.ADMIN_GENERAL}
            ]
            self.fields['commune'].initial = editor.commune_id
            if editor.role != Role.ADMIN_COMMUNE:
                self.fields['role'].choices = [
                    (r.value, r.label)
                    for r in Role
                    if r in {Role.COLLECTEUR, Role.CONTROLEUR, Role.REGISSEUR, Role.COMMERCANT, Role.MAIRE}
                ]

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get('password1'), cleaned.get('password2')
        if p1 or p2:
            if p1 != p2:
                self.add_error('password2', 'Les mots de passe ne correspondent pas.')
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        pwd = self.cleaned_data.get('password1')
        if pwd:
            user.set_password(pwd)
        if self.editor and not self.editor.is_admin_general:
            user.commune = self.editor.commune
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
