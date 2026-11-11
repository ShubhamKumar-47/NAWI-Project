"""apps/measurements/models.py – Raw measurement observation data for all OIML R 76 test procedures.

⚠ [VERIFY R76] ALL field names, units, required test points, and MPE criteria
must be verified against the official OIML R 76 edition adopted by the
testing laboratory before production use.
"""
from django.db import models
from django.conf import settings
from apps.core.constants import PassFail, WeighingTestType


class WeighingMeasurement(models.Model):
    """
    One load point in a weighing performance test (increasing or decreasing).
    ⚠ [VERIFY R76 §3.5 / Table 1] Error = indication − nominal_load; MPE from class/load table.
    """
    session = models.ForeignKey(
        "test_sessions.TestSession",
        on_delete=models.CASCADE,
        related_name="weighing_measurements",
    )
    test_type = models.CharField(
        max_length=15,
        choices=WeighingTestType.choices,
        default=WeighingTestType.INCREASING,
        verbose_name="Test Direction",
    )
    sequence_order = models.PositiveSmallIntegerField(default=1)

    # ── Measurement Data ──────────────────────────────────────────────────────
    nominal_load = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        verbose_name="Applied Reference Load",
        help_text="Nominal load applied (in display unit of instrument).",
    )
    indication = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        verbose_name="Indicated Value",
        help_text="Instrument displayed reading at this load.",
    )
    zero_indication = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=0,
        verbose_name="Zero Reading Before Load",
        help_text="Zero reading before applying load.",
    )
    tare_applied = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=0,
        verbose_name="Tare Applied",
        help_text="Tare value applied before this measurement, if any.",
    )

    # ── Computed Fields ───────────────────────────────────────────────────────
    error = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Error of Indication",
        help_text="Computed: indication − nominal_load.",
    )
    mpe = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Maximum Permissible Error (MPE)",
        help_text="Maximum Permissible Error for this load point per OIML R 76 Table 1.",
    )
    pass_fail = models.CharField(
        max_length=10,
        choices=PassFail.choices,
        default=PassFail.PENDING,
        verbose_name="Result",
    )

    # ── Conditions & Observations ─────────────────────────────────────────────
    temperature = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name="Ambient Temp (°C)",
    )
    observations = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Observations",
        help_text="Technician remarks or loading observations.",
    )
    is_draft = models.BooleanField(default=False)

    # ── Metadata ──────────────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["test_type", "sequence_order"]
        verbose_name = "Weighing Measurement"

    def __str__(self):
        return f"{self.test_type} @ {self.nominal_load} → {self.indication} [{self.pass_fail}]"


class RepeatabilityMeasurement(models.Model):
    """
    One repetition of the same nominal reference load in a repeatability test.
    ⚠ [VERIFY R76 §3.6.1] Difference between results of successive weighings of the same load
    shall not exceed the absolute value of the maximum permissible error for that load.
    """
    session = models.ForeignKey(
        "test_sessions.TestSession",
        on_delete=models.CASCADE,
        related_name="repeatability_measurements",
    )
    series_name = models.CharField(
        max_length=100,
        default="Series 1 (~0.5 Max)",
        verbose_name="Test Series",
        help_text="e.g. Series 1 (~0.5 Max), Series 2 (~Max).",
    )
    nominal_load = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        verbose_name="Reference Load",
        help_text="Nominal reference load applied for all repetitions in this series.",
    )
    repetition_number = models.PositiveSmallIntegerField(
        verbose_name="Repetition #",
        help_text="Repetition number (1, 2, 3, …). Minimum 3 repetitions required.",
    )
    zero_indication = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=0,
        verbose_name="Zero Before Load",
    )
    indication = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        verbose_name="Displayed Reading",
        help_text="Instrument indicated reading for this repetition.",
    )

    # ── Computed ──────────────────────────────────────────────────────────────
    error = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    mpe = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Acceptance criterion: Range (Max − Min) <= |MPE|.",
    )
    pass_fail = models.CharField(max_length=10, choices=PassFail.choices, default=PassFail.PENDING)

    temperature = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name="Ambient Temp (°C)",
    )
    observations = models.CharField(max_length=255, blank=True, verbose_name="Observations")
    is_draft = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )

    class Meta:
        ordering = ["series_name", "nominal_load", "repetition_number"]
        verbose_name = "Repeatability Measurement"

    def __str__(self):
        return f"{self.series_name} Rep {self.repetition_number} @ {self.nominal_load} → {self.indication} [{self.pass_fail}]"


class EccentricityMeasurement(models.Model):
    """
    One load placement position in an eccentricity (off-center loading) test.
    ⚠ [VERIFY R76 §3.6.2 & §A.4.7] Required positions and load value (typically Max/3 or Max/4).
    """
    POSITIONS = [
        ("CENTRE", "Position 1: Centre"),
        ("FRONT_LEFT", "Position 2: Front-Left (Quarter 1)"),
        ("BACK_LEFT", "Position 3: Back-Left (Quarter 2)"),
        ("BACK_RIGHT", "Position 4: Back-Right (Quarter 3)"),
        ("FRONT_RIGHT", "Position 5: Front-Right (Quarter 4)"),
    ]

    session = models.ForeignKey(
        "test_sessions.TestSession",
        on_delete=models.CASCADE,
        related_name="eccentricity_measurements",
    )
    load_position = models.CharField(
        max_length=30,
        choices=POSITIONS,
        verbose_name="Position of Load",
        help_text="Load placement position on receptor.",
    )
    nominal_load = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        verbose_name="Reference Load",
        help_text="Reference load value (e.g. approx. 1/3 Max per R 76 Table 8).",
    )
    zero_indication = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=0,
        verbose_name="Zero Before Load",
    )
    indication = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        verbose_name="Displayed Reading",
    )

    # ── Computed ──────────────────────────────────────────────────────────────
    error = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    mpe = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="MPE for eccentricity test at this load.",
    )
    pass_fail = models.CharField(max_length=10, choices=PassFail.choices, default=PassFail.PENDING)

    temperature = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name="Ambient Temp (°C)",
    )
    observations = models.CharField(max_length=255, blank=True, verbose_name="Observations")
    is_draft = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )

    class Meta:
        ordering = ["load_position"]
        verbose_name = "Eccentricity Measurement"

    def __str__(self):
        return f"Eccentricity {self.get_load_position_display()} @ {self.nominal_load} [{self.pass_fail}]"


class DiscriminationMeasurement(models.Model):
    """
    Discrimination / sensitivity test.
    ⚠ [VERIFY R76 §3.8 & §A.4.8] Extra load of 1.4d placed gently on loaded receptor shall cause
    an increase of indication of at least 1d.
    """
    session = models.ForeignKey(
        "test_sessions.TestSession",
        on_delete=models.CASCADE,
        related_name="discrimination_measurements",
    )
    test_load = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        verbose_name="Base Reference Load",
        help_text="Base test load applied (e.g. Min, 0.5 Max, or Max).",
    )
    indication_before = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        verbose_name="Indication Before Small Weight (I1)",
        help_text="Reading before additional mass is placed.",
    )
    small_weight_added = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        verbose_name="Applied Additional Load (ΔL = 1.4d)",
        help_text="Additional small weight placed gently on receptor (~1.4d).",
    )
    indication_after = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        verbose_name="Indication After Small Weight (I2)",
        help_text="Reading after additional mass is placed.",
    )

    # ── Computed ──────────────────────────────────────────────────────────────
    change = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Observed Change (I2 − I1)",
    )
    pass_fail = models.CharField(
        max_length=10,
        choices=PassFail.choices,
        default=PassFail.PENDING,
        verbose_name="Result",
    )

    temperature = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name="Ambient Temp (°C)",
    )
    observations = models.CharField(max_length=255, blank=True, verbose_name="Observations")
    is_draft = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )

    class Meta:
        verbose_name = "Discrimination Measurement"

    def __str__(self):
        return f"Discrimination @ {self.test_load}: Δ={self.change} [{self.pass_fail}]"


class TareMeasurement(models.Model):
    """
    Tare range and tare weighing performance test.
    ⚠ [VERIFY R76 §3.5.3.3 & §A.4.6] Tare weighing accuracy across tare ranges.
    """
    session = models.ForeignKey(
        "test_sessions.TestSession",
        on_delete=models.CASCADE,
        related_name="tare_measurements",
    )
    tare_load = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        verbose_name="Applied Tare Load",
        help_text="Tare value applied to receptor before test.",
    )
    net_load = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=0,
        verbose_name="Net Test Load",
        help_text="Reference net test load placed on receptor.",
    )
    gross_indication = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        verbose_name="Gross Indication",
    )
    net_indication = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        verbose_name="Net Indication",
    )

    # ── Computed ──────────────────────────────────────────────────────────────
    error = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    mpe = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="MPE for net indication.",
    )
    pass_fail = models.CharField(max_length=10, choices=PassFail.choices, default=PassFail.PENDING)

    temperature = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name="Ambient Temp (°C)",
    )
    observations = models.CharField(max_length=255, blank=True, verbose_name="Observations")
    is_draft = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )

    class Meta:
        ordering = ["tare_load"]
        verbose_name = "Tare Measurement"

    def __str__(self):
        return f"Tare @ {self.tare_load}: net={self.net_indication} err={self.error} [{self.pass_fail}]"


class ZeroSettingMeasurement(models.Model):
    """
    Zero-setting and zero-tracking test observations per OIML R 76 §A.4.1 – §A.4.3.
    """
    OPERATION_TYPES = [
        ("NON_AUTOMATIC", "Non-Automatic Zero-Setting (§A.4.1.1)"),
        ("SEMI_AUTOMATIC", "Semi-Automatic Zero-Setting (§A.4.1.2)"),
        ("AUTOMATIC", "Automatic Zero-Setting (§A.4.1.3)"),
        ("INITIAL", "Initial Zero-Setting (§A.4.1.4)"),
        ("ZERO_TRACKING", "Zero-Tracking Test (§A.4.1.5)"),
    ]

    session = models.ForeignKey(
        "test_sessions.TestSession",
        on_delete=models.CASCADE,
        related_name="zero_setting_measurements",
    )
    operation_type = models.CharField(
        max_length=40,
        choices=OPERATION_TYPES,
        default="NON_AUTOMATIC",
        verbose_name="Zero Operation",
    )
    zero_indication_before = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        verbose_name="Zero Indication Before Operation",
        help_text="Reading before activating zero function.",
    )
    zero_indication_after = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        verbose_name="Zero Indication After Operation",
        help_text="Reading after activating zero function.",
    )
    small_weight_added = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        default=0,
        verbose_name="Small Weight Added (ΔL)",
        help_text="Extra small weights placed to find turning point to next graduation.",
    )

    # ── Computed ──────────────────────────────────────────────────────────────
    calculated_error = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Zero Error (E0)",
    )
    mpe = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Zero MPE (±0.25e)",
        help_text="Maximum permissible zero error: ±0.25e per OIML R 76 §A.4.1.",
    )
    pass_fail = models.CharField(
        max_length=10,
        choices=PassFail.choices,
        default=PassFail.PENDING,
        verbose_name="Result",
    )

    temperature = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name="Ambient Temp (°C)",
    )
    observations = models.CharField(max_length=255, blank=True, verbose_name="Observations")
    is_draft = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )

    class Meta:
        ordering = ["operation_type", "-created_at"]
        verbose_name = "Zero-Setting Measurement"

    def __str__(self):
        return f"Zero-Setting {self.get_operation_type_display()}: E0={self.calculated_error} [{self.pass_fail}]"
