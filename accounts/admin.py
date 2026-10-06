from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from accounts.models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Marché', {'fields': ('telephone', 'role', 'commune', 'marche')}),
    )
    list_display = ('username', 'telephone', 'role', 'commune', 'marche', 'is_active')
    list_filter = ('role', 'commune', 'is_active')
