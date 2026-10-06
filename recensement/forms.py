from django import forms

from recensement.models import Commercant, Place


class CommercantForm(forms.ModelForm):
    class Meta:
        model = Commercant
        fields = ['nom', 'telephone', 'photo', 'actif']


class PlaceForm(forms.ModelForm):
    class Meta:
        model = Place
        fields = ['type_place', 'code', 'commercant', 'photo', 'actif']

    def __init__(self, *args, marche=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.marche = marche
        if marche:
            self.fields['type_place'].queryset = marche.types_place.filter(active=True)
            self.fields['commercant'].queryset = marche.commercants.filter(actif=True)
