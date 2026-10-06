from django.urls import path

from site_ import views

app_name = 'site_'

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('recherche/', views.RechercheView.as_view(), name='recherche'),
    path('utilisateurs/', views.UserListView.as_view(), name='utilisateurs'),
    path('utilisateurs/nouveau/', views.UserCreateView.as_view(), name='user_create'),
    path('utilisateurs/<int:pk>/', views.UserUpdateView.as_view(), name='user_update'),
]
