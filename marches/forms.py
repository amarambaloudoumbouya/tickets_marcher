from django import forms
from django.db.models import Q

from accounts.models import Role
from marches.models import Commune, Marche, PenaliteParametre, Tarif, TypePlace


class CommuneForm(forms.ModelForm):
    class Meta:
        model = Commune
        fields = ['nom', 'code', 'numero_depot', 'active']
        labels = {'numero_depot': 'Numéro Orange Money (dépôts)'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['numero_depot'].required = True


class MarcheForm(forms.ModelForm):
    class Meta:
        model = Marche
        fields = ['commune', 'nom', 'adresse', 'active', 'controle_dettes_bloquant']

    def __init__(self, *args, editor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.editor = editor
        visibles = Commune.objects.filter(suppression_demandee_le__isnull=True)
        if self.instance.commune_id:
            visibles = Commune.objects.filter(
                Q(suppression_demandee_le__isnull=True) | Q(pk=self.instance.commune_id)
            )
        self.fields['commune'].queryset = visibles
        if editor and editor.role == Role.ADMIN_COMMUNE:
            self.fields['commune'].queryset = Commune.objects.filter(pk=editor.commune_id)
            self.fields['commune'].initial = editor.commune_id
            self.fields['commune'].widget = forms.HiddenInput()

    def clean(self):
        cleaned = super().clean()
        editor = getattr(self, 'editor', None)
        if editor and editor.role == Role.ADMIN_COMMUNE:
            if not editor.commune_id:
                raise forms.ValidationError('Votre compte n’est rattaché à aucune commune.')
            self.errors.pop('commune', None)
            cleaned['commune'] = editor.commune
        return cleaned


class TypePlaceForm(forms.ModelForm):
    class Meta:
        model = TypePlace
        fields = ['nom', 'est_deambulant', 'active']


class TarifForm(forms.ModelForm):
    class Meta:
        model = Tarif
        fields = ['type_place', 'montant', 'date_debut', 'date_fin']
        widgets = {
            'date_debut': forms.DateInput(attrs={'type': 'date'}),
            'date_fin': forms.DateInput(attrs={'type': 'date'}),
        }


class PenaliteForm(forms.ModelForm):
    class Meta:
        model = PenaliteParametre
        fields = ['montant_fixe', 'pourcentage', 'majoration_par_jour']
