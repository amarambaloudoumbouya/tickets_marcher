from django.urls import path

from site_ import views

app_name = 'recensement'

urlpatterns = [
    path('commercants/', views.CommercantListView.as_view(), name='commercants'),
    path('commercants/nouveau/', views.CommercantCreateView.as_view(), name='commercant_create'),
    path('commercants/<int:pk>/', views.CommercantUpdateView.as_view(), name='commercant_update'),
    path('commercants/<int:pk>/supprimer/', views.CommercantSuppressionView.as_view(), name='commercant_supprimer'),
    path('places/', views.PlaceListView.as_view(), name='places'),
    path('places/nouveau/', views.PlaceCreateView.as_view(), name='place_create'),
]
