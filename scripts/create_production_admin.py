"""
scripts/create_production_admin.py — Idempotent Production Admin Setup.
Creates the initial superadministrator account from environment variables.
"""
import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", os.getenv("DJANGO_SETTINGS_MODULE", "config.settings.production"))
django.setup()

from apps.accounts.models import CustomUser, Organization
from apps.core.constants import UserRole


def create_admin():
    admin_email = os.getenv("ADMIN_EMAIL", "admin@nawi.local")
    admin_password = os.getenv("ADMIN_PASSWORD", "Admin@12345")
    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    org_name = os.getenv("ADMIN_ORG", "National Metrology Testing Center")
    accreditation = os.getenv("ACCREDITATION_NUMBER", "ISO-17025-NTRMS-001")

    print(f"Checking for organization: {org_name}...")
    org, _ = Organization.objects.get_or_create(
        name=org_name,
        defaults={
            "accreditation_number": accreditation,
            "is_active": True,
        },
    )

    print(f"Checking for superadmin user: {admin_email}...")
    user = CustomUser.objects.filter(email=admin_email).first()
    if not user:
        user = CustomUser.objects.create_superuser(
            email=admin_email,
            username=admin_username,
            password=admin_password,
            first_name="System",
            last_name="Administrator",
            role=UserRole.ADMINISTRATOR,
            organization=org,
            must_change_password=False,
            is_active=True,
        )
        print(f"Successfully created superadministrator: {admin_email}")
    else:
        # Ensure proper permissions and organization
        user.is_staff = True
        user.is_superuser = True
        user.organization = org
        user.role = UserRole.ADMINISTRATOR
        user.must_change_password = False
        user.save()
        print(f"Superadministrator already exists and verified: {admin_email}")


if __name__ == "__main__":
    create_admin()

