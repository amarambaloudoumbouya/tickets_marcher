from django.urls import path

from site_ import views

app_name = 'tickets'

urlpatterns = [
    path('', views.TicketListView.as_view(), name='tickets'),
    path('generer/', views.GenererTicketsView.as_view(), name='tickets_generer'),
    path('<int:pk>/', views.TicketDetailView.as_view(), name='ticket_detail'),
    path('<int:pk>/qr.png', views.TicketQrView.as_view(), name='ticket_qr'),
    path('<int:pk>/annuler/', views.TicketAnnulerView.as_view(), name='ticket_annuler'),
    path('<int:pk>/penalite/annuler/', views.PenaliteAnnulerView.as_view(), name='penalite_annuler'),
    path('impayes/', views.ImpayesListView.as_view(), name='impayes'),
    path('payer/', views.PayerView.as_view(), name='payer'),
    path('paiements/<str:token>/mock/', views.PaiementMockView.as_view(), name='paiement_mock'),
    path('paiements/<str:token>/recu/', views.RecuView.as_view(), name='recu'),
    path('controle/', views.ScanView.as_view(), name='scan'),
    path('cloture/', views.ClotureView.as_view(), name='cloture'),
    path('rapports/', views.RapportView.as_view(), name='rapports'),
    path('audit/', views.AuditListView.as_view(), name='audit'),
]
