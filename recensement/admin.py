from django.contrib import admin
from django.core.exceptions import ValidationError

from recensement.comptes import assurer_compte_commercant
from recensement.models import Commercant, Place


@admin.register(Commercant)
class CommercantAdmin(admin.ModelAdmin):
    list_display = ('nom', 'telephone', 'marche', 'actif')
    list_filter = ('marche', 'actif')
    search_fields = ('nom', 'telephone')

    def save_model(self, request, obj, form, change):
        ancien = None
        if change:
            ancien = Commercant.objects.get(pk=obj.pk).telephone
        super().save_model(request, obj, form, change)
        try:
            assurer_compte_commercant(obj, ancien_telephone=ancien)
        except ValidationError as exc:
            self.message_user(request, '; '.join(exc.messages), level='error')


@admin.register(Place)
class PlaceAdmin(admin.ModelAdmin):
    list_display = ('code', 'marche', 'commercant', 'genre', 'actif')
    list_filter = ('marche', 'genre', 'actif')
