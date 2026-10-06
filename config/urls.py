from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('comptes/', include('accounts.urls')),
    path('marches/', include('marches.urls')),
    path('recensement/', include('recensement.urls')),
    path('tickets/', include('tickets.urls')),
    path('', include('site_.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
