from django.urls import path

from site_ import views

app_name = 'recensement'

urlpatterns = [
    path('commercants/', views.CommercantListView.as_view(), name='commercants'),
    path('commercants/nouveau/', views.CommercantCreateView.as_view(), name='commercant_create'),
    path('places/', views.PlaceListView.as_view(), name='places'),
    path('places/nouveau/', views.PlaceCreateView.as_view(), name='place_create'),
]
