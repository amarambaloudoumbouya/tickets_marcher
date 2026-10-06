from django import forms


class AnnulationForm(forms.Form):
    motif = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), label='Motif')


class ScanForm(forms.Form):
    payload = forms.CharField(label='QR / numéro de ticket', widget=forms.TextInput(attrs={
        'placeholder': 'TKT-1-20260922-ABC123.signature ou numéro',
        'autofocus': True,
        'class': 'form-control form-control-lg',
    }))
