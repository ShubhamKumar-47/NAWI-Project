"""apps/measurements/views.py – Measurement data entry and observation management views.

Implements OIML R 76 test procedure observations:
- Weighing Performance Test (§A.4.4)
- Repeatability Test (§A.4.10)
- Eccentricity Test (§A.4.7)
- Discrimination Test (§A.4.8)
- Tare Weighing Test (§A.4.6)
- Zero-Setting & Tracking Tests (§A.4.1 – §A.4.3)
"""
from decimal import Decimal, InvalidOperation
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.constants import AuditAction, PassFail, WeighingTestType
from apps.audit.utils import log_action
from apps.test_sessions.models import TestSession
from .models import (
    WeighingMeasurement,
    RepeatabilityMeasurement,
    EccentricityMeasurement,
    DiscriminationMeasurement,
    TareMeasurement,
    ZeroSettingMeasurement,
)
from .forms import (
    WeighingMeasurementForm,
    RepeatabilityMeasurementForm,
    EccentricityMeasurementForm,
    DiscriminationMeasurementForm,
    TareMeasurementForm,
    ZeroSettingMeasurementForm,
)
from calculations.r76.weighing import WeighingTestCalculator
from calculations.r76.repeatability import RepeatabilityCalculator
from calculations.r76.eccentricity import EccentricityCalculator
from calculations.r76.discrimination import DiscriminationCalculator
from calculations.r76.tare import TareCalculator
from calculations.r76.zero_setting import ZeroSettingCalculator


def _get_session_or_404(request, session_pk):
    """Return the TestSession scoped to the user's organisation."""
    return get_object_or_404(
        TestSession.objects.select_related("instrument"),
        pk=session_pk,
        organization=request.user.organization,
    )


def _check_session_editable(request, session):
    """Enforce permission and session locking rules before modification."""
    if session.is_locked or session.status == "APPROVED":
        messages.error(request, "This test session is approved/locked and cannot be modified.")
        return False
    if not (request.user.is_superuser or request.user.is_administrator or request.user.is_operator):
        messages.error(request, "You do not have permission to record test observations.")
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# 1. Weighing Performance Tests (OIML R 76 §A.4.4 / §3.5)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def weighing_list(request, session_pk):
    session = _get_session_or_404(request, session_pk)
    measurements = WeighingMeasurement.objects.filter(session=session).order_by(
        "test_type", "sequence_order", "id"
    )
    increasing = measurements.filter(test_type=WeighingTestType.INCREASING)
    decreasing = measurements.filter(test_type=WeighingTestType.DECREASING)
    form = WeighingMeasurementForm()

    return render(request, "measurements/weighing_list.html", {
        "session": session,
        "instrument": session.instrument,
        "measurements": measurements,
        "increasing": increasing,
        "decreasing": decreasing,
        "form": form,
        "test_type_choices": WeighingTestType.choices,
    })


@login_required
def weighing_add(request, session_pk):
    session = _get_session_or_404(request, session_pk)
    if not _check_session_editable(request, session):
        return redirect("measurements:weighing_list", session_pk=session_pk)

    if request.method == "POST":
        form = WeighingMeasurementForm(request.POST)
        if form.is_valid():
            m = form.save(commit=False)
            m.session = session
            m.created_by = request.user

            calc = WeighingTestCalculator()
            res = calc.calculate(
                nominal_load=m.nominal_load,
                indication=m.indication,
                accuracy_class=session.instrument.accuracy_class,
                actual_scale_interval=session.instrument.actual_scale_interval,
            )
            m.error = res.error
            m.mpe = res.mpe
            m.pass_fail = res.pass_fail
            m.save()

            log_action(
                user=request.user,
                action=AuditAction.CREATE,
                obj=m,
                description=f"Added weighing measurement at {m.nominal_load} ({m.test_type}) for session {session.session_number}.",
                request=request,
            )
            messages.success(request, f"Weighing measurement saved [{m.pass_fail}].")
            return redirect("measurements:weighing_list", session_pk=session_pk)
    else:
        seq = WeighingMeasurement.objects.filter(session=session).count() + 1
        form = WeighingMeasurementForm(initial={"sequence_order": seq})

    return render(request, "measurements/weighing_add.html", {
        "session": session,
        "instrument": session.instrument,
        "form": form,
    })


@login_required
@require_POST
def weighing_batch_save(request, session_pk):
    """Batch-save multiple weighing test rows entered in dynamic table."""
    session = _get_session_or_404(request, session_pk)
    if not _check_session_editable(request, session):
        return redirect("measurements:weighing_list", session_pk=session_pk)

    is_draft = request.POST.get("action") == "draft"
    test_types = request.POST.getlist("row_test_type[]")
    nominal_loads = request.POST.getlist("row_nominal_load[]")
    indications = request.POST.getlist("row_indication[]")
    zero_indications = request.POST.getlist("row_zero_indication[]")
    tare_applieds = request.POST.getlist("row_tare_applied[]")
    temperatures = request.POST.getlist("row_temperature[]")
    observations_list = request.POST.getlist("row_observations[]")

    saved_count = 0
    calc = WeighingTestCalculator()

    try:
        with transaction.atomic():
            for i in range(len(nominal_loads)):
                load_str = nominal_loads[i].strip() if i < len(nominal_loads) else ""
                ind_str = indications[i].strip() if i < len(indications) else ""
                if not load_str or not ind_str:
                    continue

                nominal = Decimal(load_str)
                indic = Decimal(ind_str)
                z_ind = Decimal(zero_indications[i].strip()) if i < len(zero_indications) and zero_indications[i].strip() else Decimal("0")
                tare = Decimal(tare_applieds[i].strip()) if i < len(tare_applieds) and tare_applieds[i].strip() else Decimal("0")
                t_type = test_types[i] if i < len(test_types) and test_types[i] in dict(WeighingTestType.choices) else WeighingTestType.INCREASING
                obs = observations_list[i].strip() if i < len(observations_list) else ""
                temp = Decimal(temperatures[i].strip()) if i < len(temperatures) and temperatures[i].strip() else None

                res = calc.calculate(
                    nominal_load=nominal,
                    indication=indic,
                    accuracy_class=session.instrument.accuracy_class,
                    actual_scale_interval=session.instrument.actual_scale_interval,
                )

                seq = WeighingMeasurement.objects.filter(session=session, test_type=t_type).count() + 1
                m = WeighingMeasurement.objects.create(
                    session=session,
                    test_type=t_type,
                    sequence_order=seq,
                    nominal_load=nominal,
                    indication=indic,
                    zero_indication=z_ind,
                    tare_applied=tare,
                    error=res.error,
                    mpe=res.mpe,
                    pass_fail=res.pass_fail,
                    temperature=temp,
                    observations=obs,
                    is_draft=is_draft,
                    created_by=request.user,
                )
                saved_count += 1

        status_text = "saved as draft" if is_draft else "saved and validated"
        if saved_count > 0:
            log_action(
                user=request.user,
                action=AuditAction.CREATE,
                obj=session,
                description=f"Batch recorded {saved_count} weighing measurement(s) ({status_text}) for session {session.session_number}.",
                request=request,
            )
        messages.success(request, f"Successfully {status_text} {saved_count} weighing measurement(s).")
    except (InvalidOperation, ValueError, Exception) as exc:
        messages.error(request, f"Failed to batch save measurements: {exc}")

    return redirect("measurements:weighing_list", session_pk=session_pk)


@login_required
@require_POST
def weighing_delete(request, session_pk, pk):
    session = _get_session_or_404(request, session_pk)
    if not _check_session_editable(request, session):
        return redirect("measurements:weighing_list", session_pk=session_pk)

    m = get_object_or_404(WeighingMeasurement, pk=pk, session=session)
    log_action(
        user=request.user,
        action=AuditAction.DELETE,
        obj=m,
        description=f"Deleted weighing measurement #{pk} ({m.nominal_load}) from session {session.session_number}.",
        request=request,
    )
    m.delete()
    messages.success(request, "Weighing observation deleted.")
    return redirect("measurements:weighing_list", session_pk=session_pk)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Repeatability Tests (OIML R 76 §A.4.10 / §3.6.1)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def repeatability_list(request, session_pk):
    session = _get_session_or_404(request, session_pk)
    measurements = RepeatabilityMeasurement.objects.filter(session=session).order_by(
        "series_name", "nominal_load", "repetition_number"
    )

    # Group series and calculate range statistics per series
    series_dict = {}
    calc = RepeatabilityCalculator()
    for m in measurements:
        key = m.series_name
        if key not in series_dict:
            series_dict[key] = {
                "name": key,
                "nominal_load": m.nominal_load,
                "items": [],
                "indications": [],
                "range": Decimal("0"),
                "mpe": m.mpe,
                "pass_fail": PassFail.PENDING,
            }
        series_dict[key]["items"].append(m)
        series_dict[key]["indications"].append(m.indication)

    for s_name, s_data in series_dict.items():
        if len(s_data["indications"]) >= 1:
            res = calc.calculate(
                nominal_load=s_data["nominal_load"],
                indications=s_data["indications"],
                accuracy_class=session.instrument.accuracy_class,
                actual_scale_interval=session.instrument.actual_scale_interval,
            )
            s_data["range"] = res.error
            s_data["mpe"] = res.mpe
            s_data["pass_fail"] = res.pass_fail

    form = RepeatabilityMeasurementForm()

    return render(request, "measurements/repeatability_list.html", {
        "session": session,
        "instrument": session.instrument,
        "measurements": measurements,
        "series_dict": series_dict,
        "form": form,
    })


@login_required
def repeatability_add(request, session_pk):
    session = _get_session_or_404(request, session_pk)
    if not _check_session_editable(request, session):
        return redirect("measurements:repeatability_list", session_pk=session_pk)

    if request.method == "POST":
        form = RepeatabilityMeasurementForm(request.POST)
        if form.is_valid():
            m = form.save(commit=False)
            m.session = session
            m.created_by = request.user

            weigh_calc = WeighingTestCalculator()
            res = weigh_calc.calculate(
                nominal_load=m.nominal_load,
                indication=m.indication,
                accuracy_class=session.instrument.accuracy_class,
                actual_scale_interval=session.instrument.actual_scale_interval,
            )
            m.error = res.error
            m.mpe = res.mpe
            m.pass_fail = res.pass_fail
            m.save()

            log_action(
                user=request.user,
                action=AuditAction.CREATE,
                obj=m,
                description=f"Added repeatability rep #{m.repetition_number} to {m.series_name} for session {session.session_number}.",
                request=request,
            )
            messages.success(request, f"Repeatability observation recorded [{m.pass_fail}].")
            return redirect("measurements:repeatability_list", session_pk=session_pk)
    else:
        form = RepeatabilityMeasurementForm()

    return render(request, "measurements/repeatability_add.html", {
        "session": session,
        "instrument": session.instrument,
        "form": form,
    })


@login_required
@require_POST
def repeatability_batch_save(request, session_pk):
    """Batch-save an entire series of repeated measurements with range calculation."""
    session = _get_session_or_404(request, session_pk)
    if not _check_session_editable(request, session):
        return redirect("measurements:repeatability_list", session_pk=session_pk)

    is_draft = request.POST.get("action") == "draft"
    series_name = request.POST.get("series_name", "Series 1").strip()
    nominal_load_str = request.POST.get("nominal_load", "").strip()
    observations = request.POST.get("observations", "").strip()
    temp_str = request.POST.get("temperature", "").strip()

    indications_raw = request.POST.getlist("rep_indication[]")
    zero_indications_raw = request.POST.getlist("rep_zero_indication[]")

    if not nominal_load_str or not indications_raw:
        messages.error(request, "Reference load and at least one indication reading are required.")
        return redirect("measurements:repeatability_list", session_pk=session_pk)

    try:
        nominal_load = Decimal(nominal_load_str)
        temp = Decimal(temp_str) if temp_str else None
        indications = []
        zero_indications = []

        for i, ind_str in enumerate(indications_raw):
            val_str = ind_str.strip()
            if val_str:
                indications.append(Decimal(val_str))
                z_str = zero_indications_raw[i].strip() if i < len(zero_indications_raw) and zero_indications_raw[i].strip() else "0"
                zero_indications.append(Decimal(z_str))

        if not indications:
            messages.error(request, "No valid indication readings found.")
            return redirect("measurements:repeatability_list", session_pk=session_pk)

        calc = RepeatabilityCalculator()
        series_res = calc.calculate(
            nominal_load=nominal_load,
            indications=indications,
            accuracy_class=session.instrument.accuracy_class,
            actual_scale_interval=session.instrument.actual_scale_interval,
        )

        with transaction.atomic():
            start_rep = RepeatabilityMeasurement.objects.filter(session=session, series_name=series_name).count() + 1
            for idx, ind in enumerate(indications):
                z_ind = zero_indications[idx] if idx < len(zero_indications) else Decimal("0")
                RepeatabilityMeasurement.objects.create(
                    session=session,
                    series_name=series_name,
                    nominal_load=nominal_load,
                    repetition_number=start_rep + idx,
                    zero_indication=z_ind,
                    indication=ind,
                    error=ind - nominal_load,
                    mpe=series_res.mpe,
                    pass_fail=series_res.pass_fail,
                    temperature=temp,
                    observations=observations,
                    is_draft=is_draft,
                    created_by=request.user,
                )

        status_text = "saved as draft" if is_draft else "saved and evaluated"
        log_action(
            user=request.user,
            action=AuditAction.CREATE,
            obj=session,
            description=f"Recorded repeatability series '{series_name}' ({len(indications)} readings, {status_text}) for session {session.session_number}.",
            request=request,
        )
        messages.success(
            request,
            f"{series_name} ({len(indications)} readings) {status_text}. Range: {series_res.error} (MPE: ±{series_res.mpe}) [{series_res.pass_fail}]."
        )
    except (InvalidOperation, ValueError, Exception) as exc:
        messages.error(request, f"Error saving repeatability series: {exc}")

    return redirect("measurements:repeatability_list", session_pk=session_pk)


@login_required
@require_POST
def repeatability_delete(request, session_pk, pk):
    session = _get_session_or_404(request, session_pk)
    if not _check_session_editable(request, session):
        return redirect("measurements:repeatability_list", session_pk=session_pk)

    m = get_object_or_404(RepeatabilityMeasurement, pk=pk, session=session)
    m.delete()
    messages.success(request, "Repeatability observation deleted.")
    return redirect("measurements:repeatability_list", session_pk=session_pk)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Eccentricity Tests (OIML R 76 §A.4.7 / §3.6.2)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def eccentricity_list(request, session_pk):
    session = _get_session_or_404(request, session_pk)
    measurements = EccentricityMeasurement.objects.filter(session=session).order_by("load_position")
    form = EccentricityMeasurementForm()

    return render(request, "measurements/eccentricity_list.html", {
        "session": session,
        "instrument": session.instrument,
        "measurements": measurements,
        "form": form,
        "positions": EccentricityMeasurement.POSITIONS,
    })


@login_required
def eccentricity_add(request, session_pk):
    session = _get_session_or_404(request, session_pk)
    if not _check_session_editable(request, session):
        return redirect("measurements:eccentricity_list", session_pk=session_pk)

    if request.method == "POST":
        form = EccentricityMeasurementForm(request.POST)
        if form.is_valid():
            m = form.save(commit=False)
            m.session = session
            m.created_by = request.user

            calc = EccentricityCalculator()
            res = calc.calculate(
                nominal_load=m.nominal_load,
                indication=m.indication,
                position=m.load_position,
                accuracy_class=session.instrument.accuracy_class,
                actual_scale_interval=session.instrument.actual_scale_interval,
            )
            m.error = res.error
            m.mpe = res.mpe
            m.pass_fail = res.pass_fail
            m.save()

            log_action(
                user=request.user,
                action=AuditAction.CREATE,
                obj=m,
                description=f"Added eccentricity test for {m.get_load_position_display()} on session {session.session_number}.",
                request=request,
            )
            messages.success(request, f"Eccentricity measurement recorded [{m.pass_fail}].")
            return redirect("measurements:eccentricity_list", session_pk=session_pk)
    else:
        form = EccentricityMeasurementForm()

    return render(request, "measurements/eccentricity_add.html", {
        "session": session,
        "instrument": session.instrument,
        "form": form,
        "positions": EccentricityMeasurement.POSITIONS,
    })


@login_required
@require_POST
def eccentricity_batch_save(request, session_pk):
    """Batch-save eccentricity readings across the standard positions."""
    session = _get_session_or_404(request, session_pk)
    if not _check_session_editable(request, session):
        return redirect("measurements:eccentricity_list", session_pk=session_pk)

    is_draft = request.POST.get("action") == "draft"
    positions = request.POST.getlist("pos_key[]")
    nominal_loads = request.POST.getlist("pos_nominal_load[]")
    indications = request.POST.getlist("pos_indication[]")
    zero_indications = request.POST.getlist("pos_zero_indication[]")
    temperatures = request.POST.getlist("pos_temperature[]")
    observations_list = request.POST.getlist("pos_observations[]")

    calc = EccentricityCalculator()
    saved = 0

    try:
        with transaction.atomic():
            for i, pos in enumerate(positions):
                load_str = nominal_loads[i].strip() if i < len(nominal_loads) else ""
                ind_str = indications[i].strip() if i < len(indications) else ""
                if not load_str or not ind_str:
                    continue

                nominal = Decimal(load_str)
                indic = Decimal(ind_str)
                z_ind = Decimal(zero_indications[i].strip()) if i < len(zero_indications) and zero_indications[i].strip() else Decimal("0")
                temp = Decimal(temperatures[i].strip()) if i < len(temperatures) and temperatures[i].strip() else None
                obs = observations_list[i].strip() if i < len(observations_list) else ""

                res = calc.calculate(
                    nominal_load=nominal,
                    indication=indic,
                    position=pos,
                    accuracy_class=session.instrument.accuracy_class,
                    actual_scale_interval=session.instrument.actual_scale_interval,
                )

                EccentricityMeasurement.objects.update_or_create(
                    session=session,
                    load_position=pos,
                    defaults={
                        "nominal_load": nominal,
                        "indication": indic,
                        "zero_indication": z_ind,
                        "error": res.error,
                        "mpe": res.mpe,
                        "pass_fail": res.pass_fail,
                        "temperature": temp,
                        "observations": obs,
                        "is_draft": is_draft,
                        "created_by": request.user,
                    },
                )
                saved += 1

        status_text = "saved as draft" if is_draft else "saved and evaluated"
        log_action(
            user=request.user,
            action=AuditAction.CREATE,
            obj=session,
            description=f"Recorded repeatability series '{series_name}' ({len(indications)} readings, {status_text}) for session {session.session_number}.",
            request=request,
        )
        messages.success(request, f"Successfully {status_text} {saved} eccentricity position(s).")
    except (InvalidOperation, ValueError, Exception) as exc:
        messages.error(request, f"Error saving eccentricity observations: {exc}")

    return redirect("measurements:eccentricity_list", session_pk=session_pk)


@login_required
@require_POST
def eccentricity_delete(request, session_pk, pk):
    session = _get_session_or_404(request, session_pk)
    if not _check_session_editable(request, session):
        return redirect("measurements:eccentricity_list", session_pk=session_pk)

    m = get_object_or_404(EccentricityMeasurement, pk=pk, session=session)
    m.delete()
    messages.success(request, "Eccentricity measurement deleted.")
    return redirect("measurements:eccentricity_list", session_pk=session_pk)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Discrimination Tests (OIML R 76 §A.4.8 / §3.8)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def discrimination_list(request, session_pk):
    session = _get_session_or_404(request, session_pk)
    measurements = DiscriminationMeasurement.objects.filter(session=session)
    form = DiscriminationMeasurementForm()

    return render(request, "measurements/discrimination_list.html", {
        "session": session,
        "instrument": session.instrument,
        "measurements": measurements,
        "form": form,
    })


@login_required
def discrimination_add(request, session_pk):
    session = _get_session_or_404(request, session_pk)
    if not _check_session_editable(request, session):
        return redirect("measurements:discrimination_list", session_pk=session_pk)

    if request.method == "POST":
        form = DiscriminationMeasurementForm(request.POST)
        if form.is_valid():
            m = form.save(commit=False)
            m.session = session
            m.created_by = request.user

            calc = DiscriminationCalculator()
            res = calc.calculate(
                test_load=m.test_load,
                indication_before=m.indication_before,
                small_weight_added=m.small_weight_added,
                indication_after=m.indication_after,
                scale_interval=session.instrument.scale_interval,
            )
            m.change = res.error
            m.pass_fail = res.pass_fail
            m.save()

            log_action(
                user=request.user,
                action=AuditAction.CREATE,
                obj=m,
                description=f"Added discrimination test at {m.test_load} on session {session.session_number}.",
                request=request,
            )
            messages.success(request, f"Discrimination observation saved [{m.pass_fail}].")
            return redirect("measurements:discrimination_list", session_pk=session_pk)
    else:
        # Prepopulate suggested ΔL ≈ 1.4 * d
        suggested_delta = Decimal("1.4") * session.instrument.scale_interval
        form = DiscriminationMeasurementForm(initial={"small_weight_added": suggested_delta})

    return render(request, "measurements/discrimination_add.html", {
        "session": session,
        "instrument": session.instrument,
        "form": form,
    })


@login_required
@require_POST
def discrimination_batch_save(request, session_pk):
    """Batch-save multiple discrimination test observations."""
    session = _get_session_or_404(request, session_pk)
    if not _check_session_editable(request, session):
        return redirect("measurements:discrimination_list", session_pk=session_pk)

    is_draft = request.POST.get("action") == "draft"
    loads = request.POST.getlist("disc_test_load[]")
    befores = request.POST.getlist("disc_before[]")
    deltas = request.POST.getlist("disc_delta[]")
    afters = request.POST.getlist("disc_after[]")
    temps = request.POST.getlist("disc_temp[]")
    obs = request.POST.getlist("disc_obs[]")

    calc = DiscriminationCalculator()
    saved = 0

    try:
        with transaction.atomic():
            for i in range(len(loads)):
                load_str = loads[i].strip() if i < len(loads) else ""
                before_str = befores[i].strip() if i < len(befores) else ""
                delta_str = deltas[i].strip() if i < len(deltas) else ""
                after_str = afters[i].strip() if i < len(afters) else ""
                if not (load_str and before_str and delta_str and after_str):
                    continue

                test_load = Decimal(load_str)
                before = Decimal(before_str)
                delta = Decimal(delta_str)
                after = Decimal(after_str)
                temp = Decimal(temps[i].strip()) if i < len(temps) and temps[i].strip() else None
                remark = obs[i].strip() if i < len(obs) else ""

                res = calc.calculate(
                    test_load=test_load,
                    indication_before=before,
                    small_weight_added=delta,
                    indication_after=after,
                    scale_interval=session.instrument.scale_interval,
                )

                DiscriminationMeasurement.objects.create(
                    session=session,
                    test_load=test_load,
                    indication_before=before,
                    small_weight_added=delta,
                    indication_after=after,
                    change=res.error,
                    pass_fail=res.pass_fail,
                    temperature=temp,
                    observations=remark,
                    is_draft=is_draft,
                    created_by=request.user,
                )
                saved += 1

        status_text = "saved as draft" if is_draft else "saved and evaluated"
        log_action(
            user=request.user,
            action=AuditAction.CREATE,
            obj=session,
            description=f"Recorded repeatability series '{series_name}' ({len(indications)} readings, {status_text}) for session {session.session_number}.",
            request=request,
        )
        messages.success(request, f"Successfully {status_text} {saved} discrimination test(s).")
    except (InvalidOperation, ValueError, Exception) as exc:
        messages.error(request, f"Error saving discrimination records: {exc}")

    return redirect("measurements:discrimination_list", session_pk=session_pk)


@login_required
@require_POST
def discrimination_delete(request, session_pk, pk):
    session = _get_session_or_404(request, session_pk)
    if not _check_session_editable(request, session):
        return redirect("measurements:discrimination_list", session_pk=session_pk)

    m = get_object_or_404(DiscriminationMeasurement, pk=pk, session=session)
    m.delete()
    messages.success(request, "Discrimination measurement deleted.")
    return redirect("measurements:discrimination_list", session_pk=session_pk)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Tare Weighing Tests (OIML R 76 §A.4.6 / §3.5.3)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def tare_list(request, session_pk):
    session = _get_session_or_404(request, session_pk)
    measurements = TareMeasurement.objects.filter(session=session).order_by("tare_load")
    form = TareMeasurementForm()

    return render(request, "measurements/tare_list.html", {
        "session": session,
        "instrument": session.instrument,
        "measurements": measurements,
        "form": form,
    })


@login_required
def tare_add(request, session_pk):
    session = _get_session_or_404(request, session_pk)
    if not _check_session_editable(request, session):
        return redirect("measurements:tare_list", session_pk=session_pk)

    if request.method == "POST":
        form = TareMeasurementForm(request.POST)
        if form.is_valid():
            m = form.save(commit=False)
            m.session = session
            m.created_by = request.user

            calc = TareCalculator()
            res = calc.calculate(
                tare_load=m.tare_load,
                gross_indication=m.gross_indication,
                net_indication=m.net_indication,
                accuracy_class=session.instrument.accuracy_class,
                actual_scale_interval=session.instrument.actual_scale_interval,
            )
            m.error = res.error
            m.mpe = res.mpe
            m.pass_fail = res.pass_fail
            m.save()

            log_action(
                user=request.user,
                action=AuditAction.CREATE,
                obj=m,
                description=f"Added tare measurement at {m.tare_load} on session {session.session_number}.",
                request=request,
            )
            messages.success(request, f"Tare observation saved [{m.pass_fail}].")
            return redirect("measurements:tare_list", session_pk=session_pk)
    else:
        form = TareMeasurementForm()

    return render(request, "measurements/tare_add.html", {
        "session": session,
        "instrument": session.instrument,
        "form": form,
    })


@login_required
@require_POST
def tare_batch_save(request, session_pk):
    """Batch-save multiple tare test observations."""
    session = _get_session_or_404(request, session_pk)
    if not _check_session_editable(request, session):
        return redirect("measurements:tare_list", session_pk=session_pk)

    is_draft = request.POST.get("action") == "draft"
    tare_loads = request.POST.getlist("tare_load[]")
    net_loads = request.POST.getlist("tare_net_load[]")
    gross_inds = request.POST.getlist("tare_gross[]")
    net_inds = request.POST.getlist("tare_net[]")
    temps = request.POST.getlist("tare_temp[]")
    obs = request.POST.getlist("tare_obs[]")

    calc = TareCalculator()
    saved = 0

    try:
        with transaction.atomic():
            for i in range(len(tare_loads)):
                t_str = tare_loads[i].strip() if i < len(tare_loads) else ""
                n_str = net_loads[i].strip() if i < len(net_loads) else ""
                g_str = gross_inds[i].strip() if i < len(gross_inds) else ""
                net_ind_str = net_inds[i].strip() if i < len(net_inds) else ""
                if not (t_str and g_str and net_ind_str):
                    continue

                t_load = Decimal(t_str)
                n_load = Decimal(n_str) if n_str else Decimal("0")
                g_ind = Decimal(g_str)
                net_ind = Decimal(net_ind_str)
                temp = Decimal(temps[i].strip()) if i < len(temps) and temps[i].strip() else None
                remark = obs[i].strip() if i < len(obs) else ""

                res = calc.calculate(
                    tare_load=t_load,
                    gross_indication=g_ind,
                    net_indication=net_ind,
                    accuracy_class=session.instrument.accuracy_class,
                    actual_scale_interval=session.instrument.actual_scale_interval,
                )

                TareMeasurement.objects.create(
                    session=session,
                    tare_load=t_load,
                    net_load=n_load,
                    gross_indication=g_ind,
                    net_indication=net_ind,
                    error=res.error,
                    mpe=res.mpe,
                    pass_fail=res.pass_fail,
                    temperature=temp,
                    observations=remark,
                    is_draft=is_draft,
                    created_by=request.user,
                )
                saved += 1

        status_text = "saved as draft" if is_draft else "saved and evaluated"
        log_action(
            user=request.user,
            action=AuditAction.CREATE,
            obj=session,
            description=f"Recorded repeatability series '{series_name}' ({len(indications)} readings, {status_text}) for session {session.session_number}.",
            request=request,
        )
        messages.success(request, f"Successfully {status_text} {saved} tare measurement(s).")
    except (InvalidOperation, ValueError, Exception) as exc:
        messages.error(request, f"Error saving tare records: {exc}")

    return redirect("measurements:tare_list", session_pk=session_pk)


@login_required
@require_POST
def tare_delete(request, session_pk, pk):
    session = _get_session_or_404(request, session_pk)
    if not _check_session_editable(request, session):
        return redirect("measurements:tare_list", session_pk=session_pk)

    m = get_object_or_404(TareMeasurement, pk=pk, session=session)
    m.delete()
    messages.success(request, "Tare measurement deleted.")
    return redirect("measurements:tare_list", session_pk=session_pk)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Zero-Setting & Zero-Tracking Tests (OIML R 76 §A.4.1 – §A.4.3)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def zero_setting_list(request, session_pk):
    session = _get_session_or_404(request, session_pk)
    measurements = ZeroSettingMeasurement.objects.filter(session=session).order_by("operation_type", "-created_at")
    form = ZeroSettingMeasurementForm()

    return render(request, "measurements/zero_setting_list.html", {
        "session": session,
        "instrument": session.instrument,
        "measurements": measurements,
        "form": form,
        "operation_choices": ZeroSettingMeasurement.OPERATION_TYPES,
    })


@login_required
def zero_setting_add(request, session_pk):
    session = _get_session_or_404(request, session_pk)
    if not _check_session_editable(request, session):
        return redirect("measurements:zero_setting_list", session_pk=session_pk)

    if request.method == "POST":
        form = ZeroSettingMeasurementForm(request.POST)
        if form.is_valid():
            m = form.save(commit=False)
            m.session = session
            m.created_by = request.user

            calc = ZeroSettingCalculator()
            res = calc.calculate(
                zero_indication_after=m.zero_indication_after,
                scale_interval=session.instrument.scale_interval,
                actual_scale_interval=session.instrument.actual_scale_interval,
                small_weight_added=m.small_weight_added if m.small_weight_added > 0 else None,
            )
            m.calculated_error = res.error
            m.mpe = res.mpe
            m.pass_fail = res.pass_fail
            m.save()

            # Update session summary flag if all zero tests pass
            all_pass = not ZeroSettingMeasurement.objects.filter(session=session, pass_fail=PassFail.FAIL).exists()
            session.zero_test_passed = all_pass
            session.save(update_fields=["zero_test_passed"])

            log_action(
                user=request.user,
                action=AuditAction.CREATE,
                obj=m,
                description=f"Added zero-setting test ({m.operation_type}) on session {session.session_number}.",
                request=request,
            )
            messages.success(request, f"Zero-setting observation recorded [{m.pass_fail}].")
            return redirect("measurements:zero_setting_list", session_pk=session_pk)
    else:
        form = ZeroSettingMeasurementForm()

    return render(request, "measurements/zero_setting_add.html", {
        "session": session,
        "instrument": session.instrument,
        "form": form,
    })


@login_required
@require_POST
def zero_setting_batch_save(request, session_pk):
    """Batch-save multiple zero-setting/tracking checks."""
    session = _get_session_or_404(request, session_pk)
    if not _check_session_editable(request, session):
        return redirect("measurements:zero_setting_list", session_pk=session_pk)

    is_draft = request.POST.get("action") == "draft"
    ops = request.POST.getlist("zero_op[]")
    befores = request.POST.getlist("zero_before[]")
    afters = request.POST.getlist("zero_after[]")
    deltas = request.POST.getlist("zero_delta[]")
    temps = request.POST.getlist("zero_temp[]")
    obs = request.POST.getlist("zero_obs[]")

    calc = ZeroSettingCalculator()
    saved = 0

    try:
        with transaction.atomic():
            for i in range(len(ops)):
                op_type = ops[i].strip() if i < len(ops) else ""
                before_str = befores[i].strip() if i < len(befores) else ""
                after_str = afters[i].strip() if i < len(afters) else ""
                delta_str = deltas[i].strip() if i < len(deltas) else "0"
                if not (op_type and before_str and after_str):
                    continue

                before = Decimal(before_str)
                after = Decimal(after_str)
                delta = Decimal(delta_str) if delta_str else Decimal("0")
                temp = Decimal(temps[i].strip()) if i < len(temps) and temps[i].strip() else None
                remark = obs[i].strip() if i < len(obs) else ""

                res = calc.calculate(
                    zero_indication_after=after,
                    scale_interval=session.instrument.scale_interval,
                    actual_scale_interval=session.instrument.actual_scale_interval,
                    small_weight_added=delta if delta > 0 else None,
                )

                ZeroSettingMeasurement.objects.create(
                    session=session,
                    operation_type=op_type,
                    zero_indication_before=before,
                    zero_indication_after=after,
                    small_weight_added=delta,
                    calculated_error=res.error,
                    mpe=res.mpe,
                    pass_fail=res.pass_fail,
                    temperature=temp,
                    observations=remark,
                    is_draft=is_draft,
                    created_by=request.user,
                )
                saved += 1

            all_pass = not ZeroSettingMeasurement.objects.filter(session=session, pass_fail=PassFail.FAIL).exists()
            session.zero_test_passed = all_pass
            session.save(update_fields=["zero_test_passed"])

        status_text = "saved as draft" if is_draft else "saved and evaluated"
        log_action(
            user=request.user,
            action=AuditAction.CREATE,
            obj=session,
            description=f"Recorded repeatability series '{series_name}' ({len(indications)} readings, {status_text}) for session {session.session_number}.",
            request=request,
        )
        messages.success(request, f"Successfully {status_text} {saved} zero-setting check(s).")
    except (InvalidOperation, ValueError, Exception) as exc:
        messages.error(request, f"Error saving zero-setting observations: {exc}")

    return redirect("measurements:zero_setting_list", session_pk=session_pk)


@login_required
@require_POST
def zero_setting_delete(request, session_pk, pk):
    session = _get_session_or_404(request, session_pk)
    if not _check_session_editable(request, session):
        return redirect("measurements:zero_setting_list", session_pk=session_pk)

    m = get_object_or_404(ZeroSettingMeasurement, pk=pk, session=session)
    m.delete()

    all_pass = not ZeroSettingMeasurement.objects.filter(session=session, pass_fail=PassFail.FAIL).exists()
    session.zero_test_passed = all_pass
    session.save(update_fields=["zero_test_passed"])

    messages.success(request, "Zero-setting observation deleted.")
    return redirect("measurements:zero_setting_list", session_pk=session_pk)
