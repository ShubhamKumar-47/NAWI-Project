"""apps/instruments/models.py – Instrument registry model."""
from django.db import models
from django.utils import timezone
from apps.core.models import SoftDeleteModel
from apps.core.constants import AccuracyClass, InstrumentStatus


class CommonInstrumentType(models.TextChoices):
    ANALYTICAL_BALANCE = "Analytical Balance", "Analytical Balance (Class I/II)"
    PRECISION_BALANCE = "Precision Balance", "Precision Balance (Class I/II)"
    BENCH_SCALE = "Bench Scale", "Bench Scale (Class III)"
    PLATFORM_SCALE = "Platform Scale", "Platform Scale (Class III)"
    RETAIL_SCALE = "Retail / Price-Computing Scale", "Retail / Price-Computing Scale"
    CRANE_SCALE = "Crane Scale", "Crane Scale (Class III)"
    WEIGHBRIDGE = "Weighbridge / Truck Scale", "Weighbridge / Truck Scale (Class III/IIII)"
    HOPPER_SCALE = "Hopper / Tank Scale", "Hopper / Tank Scale"
    MECHANICAL_SCALE = "Mechanical Scale", "Mechanical Scale"
    HYBRID_SCALE = "Hybrid Scale", "Hybrid Scale"
    OTHER = "Other", "Other NAWI"


class MeasurementUnit(models.TextChoices):
    KG = "kg", "Kilogram (kg)"
    G = "g", "Gram (g)"
    MG = "mg", "Milligram (mg)"
    T = "t", "Tonne (t)"
    LB = "lb", "Pound (lb)"


class Instrument(SoftDeleteModel):
    """
    Represents a weighing instrument registered for OIML R 76 testing.
    All instruments are scoped to an Organisation (tenant).
    """

    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.PROTECT,
        related_name="instruments",
        verbose_name="Laboratory / Organisation",
    )

    # ── A. Instrument Identification ──────────────────────────────────────────
    instrument_name = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Instrument Name",
        help_text="Functional name, e.g. Precision Analytical Balance or Shipping Scale.",
    )
    manufacturer = models.CharField(
        max_length=200,
        verbose_name="Manufacturer",
        help_text="Name of the instrument manufacturer.",
    )
    model_name = models.CharField(
        max_length=200,
        verbose_name="Model Name / Designation",
        help_text="Model designation, e.g. XP205, Defender 3000.",
    )
    model_number = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Model Number",
        help_text="Manufacturer catalog or type model number.",
    )
    serial_number = models.CharField(
        max_length=100,
        verbose_name="Serial Number",
        help_text="Manufacturer's serial number stamped on rating plate.",
    )
    instrument_type = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Instrument Type",
        help_text="e.g. Bench Scale, Platform Scale, Analytical Balance.",
    )
    year_of_manufacture = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Year of Manufacture",
        help_text="Year instrument was manufactured.",
    )

    # ── B. Metrological Characteristics (OIML R 76) ───────────────────────────
    # ⚠ [VERIFY R76 §3.2] Accuracy class designations
    accuracy_class = models.CharField(
        max_length=10,
        choices=AccuracyClass.choices,
        verbose_name="Accuracy Class (OIML R 76)",
        help_text="OIML R 76 accuracy classification: I (Special), II (High), III (Medium), IIII (Ordinary).",
    )
    # ⚠ [VERIFY R76 §3.3] Max and Min definitions
    max_capacity = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        verbose_name="Max (Maximum Capacity)",
        help_text="Maximum capacity in the display unit.",
    )
    min_capacity = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        verbose_name="Min (Minimum Capacity)",
        help_text="Minimum capacity below which weighing errors may exceed MPE.",
    )
    # ⚠ [VERIFY R76 §3.4] Distinction between d (actual) and e (verification)
    scale_interval = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        verbose_name="d — Actual Scale Interval",
        help_text="Smallest difference between two consecutive displayed values.",
    )
    actual_scale_interval = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        verbose_name="e — Verification Scale Interval",
        help_text="Scale interval used for MPE determination per OIML R 76 Table 1.",
    )
    # ⚠ [VERIFY R76] n = Max / e
    n_max = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="n (Verification Scale Intervals)",
        help_text="n = Max / e. Auto-computed if left blank.",
    )
    unit_of_measurement = models.CharField(
        max_length=10,
        default="kg",
        verbose_name="Unit of Measurement",
        help_text="Display unit: kg, g, mg, t, lb.",
    )

    # ── C. Additional Information & Ownership ─────────────────────────────────
    customer_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Owner / Client Name",
        help_text="Client or facility that owns this instrument.",
    )
    lab_reference_number = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Laboratory Reference Number",
        help_text="Internal laboratory asset or registration ID (e.g. LAB-INS-2026-001).",
    )
    location = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Location / Bay",
        help_text="Physical lab room, bench, testing bay, or client site.",
    )
    description = models.TextField(
        blank=True,
        verbose_name="Instrument Description",
        help_text="Physical description, pan dimensions, load receptor type, and accessories.",
    )
    registration_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Registration Date",
        help_text="Date instrument was registered in the laboratory system.",
    )
    received_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Received Date",
        help_text="Date physical instrument arrived at the laboratory.",
    )
    approval_number = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Pattern Approval Number",
        help_text="Type approval certificate number (e.g. OIML / EC TAC).",
    )
    status = models.CharField(
        max_length=20,
        choices=InstrumentStatus.choices,
        default=InstrumentStatus.IN_LAB,
        verbose_name="Lab Status",
    )
    photo = models.ImageField(
        upload_to="instrument_photos/",
        null=True,
        blank=True,
        verbose_name="Instrument Photo",
    )
    notes = models.TextField(
        blank=True,
        verbose_name="Administrative Notes",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Instrument"
        verbose_name_plural = "Instruments"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "serial_number"],
                condition=models.Q(is_deleted=False),
                name="unique_serial_per_org",
            )
        ]

    def __str__(self):
        title = self.instrument_name or f"{self.manufacturer} {self.model_name}"
        return f"{title} (S/N: {self.serial_number})"

    def save(self, *args, **kwargs):
        """Auto-populate fields and compute n = Max / e if not provided."""
        if not self.instrument_name:
            self.instrument_name = f"{self.manufacturer} {self.model_name}".strip()
        if not self.registration_date:
            self.registration_date = timezone.now().date()
        if not self.received_date and self.registration_date:
            self.received_date = self.registration_date
        if (
            not self.n_max
            and self.max_capacity
            and self.actual_scale_interval
            and self.actual_scale_interval > 0
        ):
            # ⚠ [VERIFY R76] Confirm n_max formula: n = Max / e
            self.n_max = int(self.max_capacity / self.actual_scale_interval)
        super().save(*args, **kwargs)

    @property
    def unit_of_measure(self):
        """Convenience alias for unit_of_measurement."""
        return self.unit_of_measurement

    @property
    def display_name(self):
        """Human-readable manufacturer + model combination."""
        return self.instrument_name or f"{self.manufacturer} {self.model_name}"

    @property
    def verification_interval_e(self):
        """Alias for verification scale interval (e)."""
        return self.actual_scale_interval

    @property
    def actual_interval_d(self):
        """Alias for actual scale interval (d)."""
        return self.scale_interval

    @property
    def e_equals_d(self):
        """Whether verification interval e equals actual scale interval d."""
        return self.actual_scale_interval == self.scale_interval

    @property
    def has_test_records(self):
        """Return True if any test session is associated with this instrument."""
        return self.test_sessions.exists()

    @property
    def has_approved_tests(self):
        """Return True if any approved (certified) test session exists."""
        from apps.core.constants import SessionStatus
        return self.test_sessions.filter(status=SessionStatus.APPROVED).exists()
