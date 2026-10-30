from django import forms

from marches.models import TypePlace
from recensement.models import Commercant, Place


class CommercantForm(forms.ModelForm):
    type_place = forms.ModelChoiceField(label='Type de place', queryset=TypePlace.objects.none())
    code = forms.CharField(
        label='Code de la place',
        max_length=40,
        help_text='Numéro de boutique, de table, ou code déambulant.',
    )
    photo_place = forms.ImageField(label='Photo de la place', required=False)

    class Meta:
        model = Commercant
        fields = ['nom', 'telephone', 'photo', 'actif']
        labels = {
            'photo': 'Photo du commerçant',
        }

    def __init__(self, *args, marche=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.marche = marche
        self.place = None
        if marche:
            self.fields['type_place'].queryset = marche.types_place.filter(active=True)
        self.order_fields(['nom', 'telephone', 'photo', 'type_place', 'code', 'photo_place', 'actif'])

    def clean_telephone(self):
        telephone = self.cleaned_data['telephone'].strip()
        if self.marche and Commercant.objects.filter(
            marche=self.marche, telephone=telephone, supprime_le__isnull=True,
        ).exists():
            raise forms.ValidationError('Ce téléphone est déjà recensé sur ce marché.')
        return telephone

    def clean_code(self):
        code = self.cleaned_data['code'].strip()
        if self.marche and Place.objects.filter(
            marche=self.marche, code=code, commercant__supprime_le__isnull=True,
        ).exists():
            raise forms.ValidationError('Ce code est déjà utilisé sur ce marché.')
        return code

    def save(self, commit=True):
        commercant = super().save(commit=commit)
        if commit:
            self.place = Place.objects.create(
                marche=commercant.marche,
                type_place=self.cleaned_data['type_place'],
                code=self.cleaned_data['code'],
                commercant=commercant,
                photo=self.cleaned_data.get('photo_place') or None,
                actif=commercant.actif,
                created_by=commercant.created_by,
            )
        return commercant


class CommercantUpdateForm(forms.ModelForm):
    class Meta:
        model = Commercant
        fields = ['nom', 'telephone', 'photo', 'actif']
        labels = {'photo': 'Photo du commerçant'}

    def clean_telephone(self):
        telephone = self.cleaned_data['telephone'].strip()
        doublon = Commercant.objects.filter(
            marche_id=self.instance.marche_id, telephone=telephone, supprime_le__isnull=True,
        )
        if self.instance.pk:
            doublon = doublon.exclude(pk=self.instance.pk)
        if doublon.exists():
            raise forms.ValidationError('Ce téléphone est déjà recensé sur ce marché.')
        return telephone


class CommercantSuppressionForm(forms.Form):
    motif = forms.CharField(label='Motif', widget=forms.Textarea(attrs={'rows': 3}))

    def clean_motif(self):
        motif = self.cleaned_data['motif'].strip()
        if not motif:
            raise forms.ValidationError('Indiquez le motif de la suppression.')
        return motif
