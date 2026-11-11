"""apps/accounts/admin.py – Admin registration for accounts app."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ["name", "accreditation_number", "email", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["name", "accreditation_number", "email"]


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ["email", "first_name", "last_name", "role", "organization", "is_active"]
    list_filter = ["role", "is_active", "organization"]
    search_fields = ["email", "first_name", "last_name"]
    ordering = ["last_name", "first_name"]
    fieldsets = UserAdmin.fieldsets + (
        ("NTRMS Fields", {
            "fields": ("role", "organization", "job_title", "phone", "signature_image", "must_change_password")
        }),
    )
