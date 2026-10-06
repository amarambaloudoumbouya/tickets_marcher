from django import forms


class MarcheSelectForm(forms.Form):
    marche = forms.ModelChoiceField(queryset=None, label='Marché')

    def __init__(self, *args, queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['marche'].queryset = queryset
