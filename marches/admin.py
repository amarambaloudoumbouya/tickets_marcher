from django.contrib import admin

from marches.models import Commune, Marche, PenaliteParametre, Tarif, TypePlace


@admin.register(Commune)
class CommuneAdmin(admin.ModelAdmin):
    list_display = ('nom', 'code', 'active')


@admin.register(Marche)
class MarcheAdmin(admin.ModelAdmin):
    list_display = ('nom', 'commune', 'active')
    list_filter = ('commune', 'active')


admin.site.register(TypePlace)
admin.site.register(Tarif)
admin.site.register(PenaliteParametre)
