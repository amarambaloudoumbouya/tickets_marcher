from django import forms
from django.db.models import Q

from marches.models import Commune, Marche, PenaliteParametre, Tarif, TypePlace


class CommuneForm(forms.ModelForm):
    class Meta:
        model = Commune
        fields = ['nom', 'code', 'active']


class MarcheForm(forms.ModelForm):
    class Meta:
        model = Marche
        fields = ['commune', 'nom', 'adresse', 'active', 'controle_dettes_bloquant']

    def __init__(self, *args, editor=None, **kwargs):
        super().__init__(*args, **kwargs)
        visibles = Commune.objects.filter(suppression_demandee_le__isnull=True)
        if self.instance.commune_id:
            visibles = Commune.objects.filter(
                Q(suppression_demandee_le__isnull=True) | Q(pk=self.instance.commune_id)
            )
        self.fields['commune'].queryset = visibles
        if editor and not editor.is_admin_general:
            self.fields['commune'].queryset = Commune.objects.filter(pk=editor.commune_id)
            self.fields['commune'].initial = editor.commune_id


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
