"""calculations/models.py – Persistent storage for OIML R 76 calculation results and audit traceability."""
from django.db import models
from django.conf import settings


class CalculationCompliance(models.TextChoices):
    PASS = "PASS", "Pass"
    FAIL = "FAIL", "Fail"
    NOT_EVALUATED = "NOT_EVALUATED", "Not Evaluated"


class CalculationProcedureType(models.TextChoices):
    WEIGHING = "WEIGHING", "Weighing Performance Test (§A.4.4)"
    REPEATABILITY = "REPEATABILITY", "Repeatability Test (§A.4.10)"
    ECCENTRICITY = "ECCENTRICITY", "Eccentricity Test (§A.4.7)"
    DISCRIMINATION = "DISCRIMINATION", "Discrimination Test (§A.4.8)"
    TARE = "TARE", "Tare Weighing Test (§A.4.6)"
    ZERO_SETTING = "ZERO_SETTING", "Zero-Setting & Tracking Test (§A.4.1)"


class CalculationRecord(models.Model):
    """
    Persisted calculation output and compliance evaluation for an OIML R 76 test observation.
    Maintains explicit traceability between original raw readings, applied rule versions,
    calculated errors, permissible errors, and human-readable explanations.
    """
    session = models.ForeignKey(
        "test_sessions.TestSession",
        on_delete=models.CASCADE,
        related_name="calculation_records",
        verbose_name="Test Session",
    )
    procedure_type = models.CharField(
        max_length=30,
        choices=CalculationProcedureType.choices,
        verbose_name="Procedure Type",
    )
    sequence_number = models.PositiveSmallIntegerField(
        default=1,
        verbose_name="Sequence #",
    )
    title = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Observation / Series Title",
        help_text="e.g. 'Increasing Load @ 50.0000 g' or 'Series 1 Repeatability'",
    )

    # ── Rule Set & Standard Versioning ─────────────────────────────────────────
    standard_edition = models.CharField(
        max_length=100,
        default="OIML R 76-1:2006",
        verbose_name="Applicable Standard Edition",
        help_text="Standard governing this evaluation (e.g. OIML R 76-1:2006).",
    )
    rule_version = models.CharField(
        max_length=50,
        default="R76-2006-v1.0",
        verbose_name="Rule Version",
        help_text="Version identifier of calculation rule set.",
    )
    standard_clause = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Standard Clause / Table Reference",
        help_text="e.g. OIML R 76-1 §A.4.4 / Table 1",
    )
    is_rule_configured = models.BooleanField(
        default=True,
        verbose_name="Rule Configured",
        help_text="False if rule or tolerance table is not verified/configured in the engine.",
    )

    # ── Metrological Values & Results ──────────────────────────────────────────
    reference_load = models.DecimalField(
        max_digits=14,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Reference Test Load (L)",
    )
    indicated_reading = models.DecimalField(
        max_digits=14,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Indicated Value (I)",
    )
    zero_indication = models.DecimalField(
        max_digits=14,
        decimal_places=6,
        default=0,
        verbose_name="Zero Reading (I0)",
    )
    corrected_reading = models.DecimalField(
        max_digits=14,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Corrected Indication",
    )
    calculated_error = models.DecimalField(
        max_digits=14,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Calculated Error (E)",
    )
    permissible_error_mpe = models.DecimalField(
        max_digits=14,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Maximum Permissible Error (MPE)",
    )
    comparison_result = models.CharField(
        max_length=20,
        choices=CalculationCompliance.choices,
        default=CalculationCompliance.NOT_EVALUATED,
        verbose_name="Comparison Result",
    )
    explanation = models.TextField(
        blank=True,
        verbose_name="Mathematical & Metrological Explanation",
        help_text="Step-by-step formula and rule evaluation rationale.",
    )

    # ── Traceability to Raw Observations ──────────────────────────────────────
    measurement_model = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Source Model Name",
        help_text="e.g. WeighingMeasurement, RepeatabilityMeasurement",
    )
    measurement_reference_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Source Measurement PK",
        help_text="Primary key of source measurement record for audit trail.",
    )
    raw_data_snapshot = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Raw Data Snapshot",
        help_text="Input observation parameters captured at calculation time.",
    )
    computed_metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Computed Metadata",
        help_text="Intermediate calculation parameters (load in e, turning point, etc.).",
    )

    # ── Metadata ──────────────────────────────────────────────────────────────
    calculated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Calculated Timestamp",
    )
    calculated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Calculated By",
    )

    class Meta:
        ordering = ["procedure_type", "sequence_number", "id"]
        verbose_name = "Calculation Record"
        verbose_name_plural = "Calculation Records"

    def __str__(self):
        return f"{self.procedure_type} #{self.sequence_number}: Error={self.calculated_error} (MPE=±{self.permissible_error_mpe}) [{self.comparison_result}]"

