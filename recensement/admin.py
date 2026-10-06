from django.contrib import admin

from recensement.models import Commercant, Place


@admin.register(Commercant)
class CommercantAdmin(admin.ModelAdmin):
    list_display = ('nom', 'telephone', 'marche', 'actif')
    list_filter = ('marche', 'actif')
    search_fields = ('nom', 'telephone')


@admin.register(Place)
class PlaceAdmin(admin.ModelAdmin):
    list_display = ('code', 'marche', 'commercant', 'genre', 'actif')
    list_filter = ('marche', 'genre', 'actif')
