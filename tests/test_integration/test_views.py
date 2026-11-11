"""tests/test_integration/test_views.py – Integration tests for web views and workflows."""
from django.test import TestCase, Client
from django.urls import reverse
from apps.accounts.models import CustomUser, Organization
from apps.core.constants import UserRole


class TestWebViews(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organization.objects.create(name="Test Metrology Lab")
        self.user = CustomUser.objects.create_user(
            email="tech@test.local",
            username="tech_test",
            password="Password123!",
            role=UserRole.TECHNICIAN,
            organization=self.org,
            must_change_password=False,
        )

    def test_homepage_unauthenticated(self):
        """Unauthenticated user receives landing page (200 OK)."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "NAWI Test Report Management System")
        self.assertContains(response, "Sign In")

    def test_homepage_authenticated(self):
        """Authenticated user sees dashboard (200 OK)."""
        self.client.login(username="tech@test.local", password="Password123!")
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard")
        self.assertContains(response, "Total Instruments")

    def test_instruments_list_view(self):
        """Technician can access instruments list."""
        self.client.login(username="tech@test.local", password="Password123!")
        response = self.client.get(reverse("instruments:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Instrument Registry")

