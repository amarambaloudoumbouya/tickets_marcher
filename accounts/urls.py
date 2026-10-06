from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from accounts import views
from accounts.forms import LoginForm

app_name = 'accounts'

urlpatterns = [
    path('connexion/', LoginView.as_view(template_name='registration/login.html', authentication_form=LoginForm), name='login'),
    path('deconnexion/', LogoutView.as_view(), name='logout'),
    path('profil/', views.ProfilView.as_view(), name='profil'),
    path('mot-de-passe/', views.MotDePasseView.as_view(), name='password_change'),
    path('verrouiller/', views.LockView.as_view(), name='lock'),
    path('deverrouiller/', views.UnlockView.as_view(), name='unlock'),
]
