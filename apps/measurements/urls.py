"""apps/measurements/urls.py – URLs for OIML R 76 observation & measurement recording."""
from django.urls import path
from . import views

app_name = "measurements"

urlpatterns = [
    # ── 1. Weighing Performance Tests ──────────────────────────────────────────
    path("<uuid:session_pk>/weighing/", views.weighing_list, name="weighing_list"),
    path("<uuid:session_pk>/weighing/add/", views.weighing_add, name="weighing_add"),
    path("<uuid:session_pk>/weighing/batch-save/", views.weighing_batch_save, name="weighing_batch_save"),
    path("<uuid:session_pk>/weighing/<int:pk>/delete/", views.weighing_delete, name="weighing_delete"),

    # ── 2. Repeatability Tests ────────────────────────────────────────────────
    path("<uuid:session_pk>/repeatability/", views.repeatability_list, name="repeatability_list"),
    path("<uuid:session_pk>/repeatability/add/", views.repeatability_add, name="repeatability_add"),
    path("<uuid:session_pk>/repeatability/batch-save/", views.repeatability_batch_save, name="repeatability_batch_save"),
    path("<uuid:session_pk>/repeatability/<int:pk>/delete/", views.repeatability_delete, name="repeatability_delete"),

    # ── 3. Eccentricity Tests ─────────────────────────────────────────────────
    path("<uuid:session_pk>/eccentricity/", views.eccentricity_list, name="eccentricity_list"),
    path("<uuid:session_pk>/eccentricity/add/", views.eccentricity_add, name="eccentricity_add"),
    path("<uuid:session_pk>/eccentricity/batch-save/", views.eccentricity_batch_save, name="eccentricity_batch_save"),
    path("<uuid:session_pk>/eccentricity/<int:pk>/delete/", views.eccentricity_delete, name="eccentricity_delete"),

    # ── 4. Discrimination Tests ───────────────────────────────────────────────
    path("<uuid:session_pk>/discrimination/", views.discrimination_list, name="discrimination_list"),
    path("<uuid:session_pk>/discrimination/add/", views.discrimination_add, name="discrimination_add"),
    path("<uuid:session_pk>/discrimination/batch-save/", views.discrimination_batch_save, name="discrimination_batch_save"),
    path("<uuid:session_pk>/discrimination/<int:pk>/delete/", views.discrimination_delete, name="discrimination_delete"),

    # ── 5. Tare Tests ─────────────────────────────────────────────────────────
    path("<uuid:session_pk>/tare/", views.tare_list, name="tare_list"),
    path("<uuid:session_pk>/tare/add/", views.tare_add, name="tare_add"),
    path("<uuid:session_pk>/tare/batch-save/", views.tare_batch_save, name="tare_batch_save"),
    path("<uuid:session_pk>/tare/<int:pk>/delete/", views.tare_delete, name="tare_delete"),

    # ── 6. Zero-Setting & Tracking Tests ──────────────────────────────────────
    path("<uuid:session_pk>/zero-setting/", views.zero_setting_list, name="zero_setting_list"),
    path("<uuid:session_pk>/zero-setting/add/", views.zero_setting_add, name="zero_setting_add"),
    path("<uuid:session_pk>/zero-setting/batch-save/", views.zero_setting_batch_save, name="zero_setting_batch_save"),
    path("<uuid:session_pk>/zero-setting/<int:pk>/delete/", views.zero_setting_delete, name="zero_setting_delete"),
]
