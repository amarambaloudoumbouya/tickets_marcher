from django.contrib import admin

from tickets.models import ClotureJournee, JournalAudit, Paiement, Ticket


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('numero', 'date_validite', 'commercant', 'montant', 'montant_penalite', 'statut')
    list_filter = ('statut', 'marche', 'date_validite')
    search_fields = ('numero',)
    readonly_fields = ('numero', 'signature', 'montant', 'date_validite')


admin.site.register(Paiement)
admin.site.register(ClotureJournee)
admin.site.register(JournalAudit)
