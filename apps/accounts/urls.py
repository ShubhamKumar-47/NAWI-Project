"""apps/accounts/urls.py – URL routing for authentication and user management."""
from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    # Authentication
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.profile_view, name="profile"),
    path("password/change/", views.password_change_view, name="password_change"),

    # Password Reset Workflow
    path("password/reset/", views.CustomPasswordResetView.as_view(), name="password_reset"),
    path("password/reset/done/", views.CustomPasswordResetDoneView.as_view(), name="password_reset_done"),
    path("password/reset/<uidb64>/<token>/", views.CustomPasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("password/reset/complete/", views.CustomPasswordResetCompleteView.as_view(), name="password_reset_complete"),

    # User Management (Administrator & Lab Manager)
    path("users/", views.UserListView.as_view(), name="user_list"),
    path("users/create/", views.UserCreateView.as_view(), name="user_create"),
    path("users/<uuid:pk>/", views.UserDetailView.as_view(), name="user_detail"),

    # Organization Multi-Tenancy (Administrator only)
    path("organizations/", views.OrganizationListView.as_view(), name="org_list"),
    path("organizations/create/", views.OrganizationCreateView.as_view(), name="org_create"),
    path("organizations/<uuid:pk>/edit/", views.OrganizationUpdateView.as_view(), name="org_edit"),

    # Security & Error Pages
    path("lockout/", views.lockout_view, name="lockout"),
    path("unauthorized/", views.unauthorized_view, name="unauthorized"),
]
