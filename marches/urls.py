from django.urls import path

from site_ import views

app_name = 'marches'

urlpatterns = [
    path('communes/', views.CommuneListView.as_view(), name='communes'),
    path('communes/nouveau/', views.CommuneCreateView.as_view(), name='commune_create'),
    path('communes/<int:pk>/', views.CommuneUpdateView.as_view(), name='commune_update'),
    path('communes/<int:pk>/supprimer/', views.CommuneSuppressionView.as_view(), name='commune_supprimer'),
    path('communes/<int:pk>/valider-suppression/', views.CommuneValiderSuppressionView.as_view(), name='commune_valider_suppression'),
    path('communes/<int:pk>/recuperer/', views.CommuneRecupererView.as_view(), name='commune_recuperer'),
    path('', views.MarcheListView.as_view(), name='marches'),
    path('nouveau/', views.MarcheCreateView.as_view(), name='marche_create'),
    path('<int:pk>/', views.MarcheUpdateView.as_view(), name='marche_update'),
    path('<int:pk>/supprimer/', views.MarcheSuppressionView.as_view(), name='marche_supprimer'),
    path('<int:pk>/valider-suppression/', views.MarcheValiderSuppressionView.as_view(), name='marche_valider_suppression'),
    path('<int:pk>/recuperer/', views.MarcheRecupererView.as_view(), name='marche_recuperer'),
    path('types-place/', views.TypePlaceListView.as_view(), name='types_place'),
    path('types-place/nouveau/', views.TypePlaceCreateView.as_view(), name='typeplace_create'),
    path('tarifs/', views.TarifListView.as_view(), name='tarifs'),
    path('tarifs/nouveau/', views.TarifCreateView.as_view(), name='tarif_create'),
    path('penalite/', views.PenaliteUpdateView.as_view(), name='penalite'),
]
