# NAWI Test Report Management System (NTRMS)

[![OIML R 76-1:2006](https://img.shields.io/badge/Standard-OIML%20R%2076--1%3A2006-0d6efd.svg)](https://www.oiml.org/)
[![ISO/IEC 17025](https://img.shields.io/badge/Accreditation-ISO%2FIEC%2017025-10b981.svg)](https://www.iso.org/standard/67198.html)
[![Django 5.0](https://img.shields.io/badge/Framework-Django%205.0-092e20.svg)](https://www.djangoproject.com/)
[![Tests](https://img.shields.io/badge/Test%20Suite-128%20Passing-success.svg)]()

An enterprise-grade Laboratory Information Management System (LIMS) designed for testing, verification, and certification of **Non-Automatic Weighing Instruments (NAWI)** in strict conformance with **OIML Recommendation R 76-1 (Edition 2006)** and **ISO/IEC 17025:2017**.

---

## Table of Contents
1. [Core Features & Capabilities](#core-features--capabilities)
2. [Metrological Calculation Engine & OIML R 76 Compliance](#metrological-calculation-engine--oiml-r-76-compliance)
3. [End-to-End Metrological Workflow](#end-to-end-metrological-workflow)
4. [Dual Report Generation (PDF & Word)](#dual-report-generation-pdf--word)
5. [Audit Trail & Controlled Revision Protocol](#audit-trail--controlled-revision-protocol)
6. [System Architecture & Apps](#system-architecture--apps)
7. [Local Development Setup](#local-development-setup)
8. [Database Setup Instructions (PostgreSQL)](#database-setup-instructions-postgresql)
9. [Deployment on Render](#deployment-on-render)
10. [Database Backups](#database-backups)
11. [Administrator Account Setup](#administrator-account-setup)
12. [Running the Test Suite](#running-the-test-suite)

---

## Core Features & Capabilities

- **Instrument Management Registry**: Complete tracking of weighing instruments with automated verification interval verification ($n = Max / e$, $d \le e$), pattern approval numbers, and client linkages.
- **Test Session Wizard**: 5-step guided wizard for configuring test environmental conditions, equipment identification, and applicable test procedures.
- **Dynamic Batch Observation Forms**: Real-time measurement input tables for weighing, repeatability, eccentricity, discrimination, tare, and zero-setting.
- **Automated Python Decimal Calculation Engine**: High-precision calculation service layer operating strictly with Python `Decimal` to eliminate floating-point drift.
- **Role-Based Workflow Governance (RBAC)**: Enforced segregation of duties between Technicians (`operator`), Technical Reviewers (`reviewer`), and Administrators (`admin`).
- **Synchronized Dual Report Generation**: Produces formal cryptographically hashed (SHA-256) ReportLab PDF certificates and matching editable Microsoft Word (`.docx`) test documentation under identical revision lineage.
- **Point-in-Time Data Snapshots**: Approved reports permanently freeze complete metrological readings, environmental ratings, and compliance tables as immutable JSON data snapshots.
- **Controlled Revision Protocol**: ISO/IEC 17025 §7.8.8 compliant change-control mechanism requiring authorized reviewer sign-off and mandatory change justifications (minimum 15 characters).
- **Comprehensive Audit Trail**: Real-time logging of user logins, instrument modifications, draft observations, approval transitions, and download events.

---

## Metrological Calculation Engine & OIML R 76 Compliance

The calculation engine is isolated in [`calculations/services/`](file:///d:/NAWI%20Project/calculations/services/) and implements the full criteria of **OIML R 76-1:2006 Table 1**:

### Maximum Permissible Error (MPE) Limits on Initial Verification

| Accuracy Class | Zone 1: $\pm 0.5\ e$ | Zone 2: $\pm 1.0\ e$ | Zone 3: $\pm 1.5\ e$ |
|---|---|---|---|
| **Class I** | $0 \le m \le 50,000\ e$ | $50,000\ e < m \le 200,000\ e$ | $m > 200,000\ e$ |
| **Class II** | $0 \le m \le 5,000\ e$ | $5,000\ e < m \le 20,000\ e$ | $m > 20,000\ e$ |
| **Class III** | $0 \le m \le 500\ e$ | $500\ e < m \le 2,000\ e$ | $m > 2,000\ e$ |
| **Class IIII** | $0 \le m \le 50\ e$ | $50\ e < m \le 200\ e$ | $m > 200\ e$ |

### Supported Metrological Test Procedures

1. **Weighing Performance (§A.4.4)**:
   - Error evaluated as $E = I - L$ (or corrected error $E_c = I + 0.5d - \Delta L - L$).
   - Evaluates at least 5 roughly equal load steps from zero up to and including $Max$ and back to zero.
2. **Repeatability (§A.4.10 / §3.6.1)**:
   - Multi-series repeated measurements (at $0.5\ Max$ and $Max$).
   - Acceptance criterion: Dispersion range $R = I_{max} - I_{min} \le |mpe|$ for the applied reference load.
3. **Eccentricity (§A.4.7 / §3.6.2)**:
   - Off-center load placement ($1/3\ Max$ or $1/4$ for 4-point supports).
   - Error at each off-center position must satisfy $|E| \le |mpe|$.
4. **Discrimination (§A.4.8 / §3.8)**:
   - Extra load of $1.4\ d$ placed gently on the loaded pan must produce a clear indicated reading shift of at least $1\ d$.
5. **Zero-Setting & Zero-Tracking (§A.4.1 – §A.4.3 / §4.5)**:
   - Evaluates zero-setting error $E_0 \le \pm 0.25\ e$.
6. **Tare Balancing (§A.4.6)**:
   - Evaluates tare accuracy and net weighing error within applicable MPE zones.

---

## End-to-End Metrological Workflow

```mermaid
flowchart LR
    A["1. Login<br>(Technician)"] --> B["2. Register Instrument<br>(OIML Specs)"]
    B --> C["3. Create Test Session<br>(Wizard)"]
    C --> D["4. Enter Observations<br>(Batch Table)"]
    D --> E["5. Automated Calculations<br>(OIML Engine)"]
    E --> F["6. Submit for Review<br>(Technician)"]
    F --> G["7. Technical Inspection<br>(Reviewer)"]
    G --> H{"Approved?"}
    H -- "Yes" --> I["8. Approve & Lock Record"]
    H -- "No" --> J["Return for Correction<br>(Mandatory Reason)"]
    J --> D
    I --> K["9. Generate Reports<br>(PDF & Word)"]
    K --> L["10. Download & Audit Logging"]
    L --> M["11. Controlled Revision<br>(If Amended)"]
```

---

## Dual Report Generation (PDF & Word)

- **ReportLab PDF Certificate**:
  - Page 1: Official Laboratory Header, Unique Report UUID, Metrological Instrument Ratings.
  - Page 2: Environmental Conditions & Traceable Standards Equipment Table.
  - Page 3: Measurement Observation & Error Evaluation Tables with Compliance Badges.
  - Page 4: Summary of Results, Conformity Statement, and Reviewer Digital Signatory Block.
- **python-docx Microsoft Word Document**:
  - Generates an identical, fully editable `.docx` document matching the PDF certificate's exact layout, tables, formatting, and revision number.

---

## Audit Trail & Controlled Revision Protocol

- **Immutable Data Snapshots**: The moment a report is generated, an exact point-in-time snapshot of the session metadata, instrument parameters, and all measurement points is stored in `GeneratedReport.data_snapshot` JSON.
- **Deletion Prevention**: Calling `.delete()` on an approved session or report raises `PermissionDenied`. The Django admin explicitly disables report deletion.
- **Controlled Revision**:
  1. Only authorized reviewers or administrators can unlock an approved test.
  2. Requires a mandatory technical justification (minimum 15 characters).
  3. The active report is marked `is_superseded = True` while permanently retaining its file and snapshot.
  4. The session is incremented (`revision_number = 2`, e.g., `-R02`).
  5. Generating a revised report bi-directionally links `superseded_by` to the new version.

---

## System Architecture & Apps

```text
nawi-project/
├── apps/
│   ├── core/           # Constants, base models, context processors
│   ├── accounts/       # User authentication, RBAC, multi-tenant organizations
│   ├── instruments/    # Instrument registry, OIML pattern validation
│   ├── test_sessions/  # Test session wizard, reviewer dashboard, approval service
│   ├── measurements/   # Dynamic observation entry forms & batch save endpoints
│   ├── reports/        # ReportLab PDF & python-docx builders, audit trail & revisions
│   ├── dashboard/      # Laboratory KPI dashboard, Chart.js metrics, settings
│   └── audit/          # Immutable system audit trail & download access logs
├── calculations/       # Pure-Python Decimal OIML R 76 calculation service layer
├── config/             # Django settings (base, development, production, testing)
├── static/             # LIMS CSS design system & client-side JavaScript controllers
├── templates/          # Responsive Bootstrap 5 laboratory templates
└── tests/              # Comprehensive test suites (128 passing tests)
```

---

## Local Development Setup

### 1. Clone & Set Up Virtual Environment

```bash
cd "NAWI Project"
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Copy the `.env.example` template to `.env`:

```bash
copy .env.example .env
```

### 4. Run Migrations & Seed Demo Data

```bash
python manage.py migrate
python scripts/seed_demo_data.py
```

### 5. Launch the Development Server

```bash
python manage.py runserver
```

Open [http://localhost:8000/](http://localhost:8000/) in your browser.

---

## Database Setup Instructions (PostgreSQL)

For production, NTRMS requires a PostgreSQL database (version 14 or higher).

### 1. Install PostgreSQL & Create Database

```sql
-- Connect as postgres superuser
CREATE DATABASE nawi_trms;
CREATE USER nawi_user WITH PASSWORD 'StrongPassword123!';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE nawi_trms TO nawi_user;
ALTER DATABASE nawi_trms OWNER TO nawi_user;
```

### 2. Configure `DATABASE_URL`

In `.env`:

```env
DATABASE_URL=postgres://nawi_user:StrongPassword123!@localhost:5432/nawi_trms
```

### 3. Run Production Migrations

```bash
python manage.py migrate --settings=config.settings.production
```

---

## Deployment on Render

NTRMS is fully configured for deployment on [Render](https://render.com/) using the included [`render.yaml`](file:///d:/NAWI%20Project/render.yaml) blueprint.

### Method 1: Automatic Blueprint Deployment (Recommended)

1. Push your repository to GitHub or GitLab.
2. Log in to [Render Dashboard](https://dashboard.render.com/).
3. Click **New +** $\to$ **Blueprint**.
4. Connect your repository. Render automatically reads `render.yaml` and provisions:
   - **Web Service**: Gunicorn WSGI web application with WhiteNoise static files.
   - **PostgreSQL Database**: Managed PostgreSQL 16 database.
   - **Persistent Disk**: 10 GB disk volume mounted at `/var/data/media` for report files.
5. Click **Apply**.

### Method 2: Manual Web Service Setup

If setting up manually in Render:

1. **Environment**: Python
2. **Build Command**: `./build.sh`
3. **Start Command**: `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 4 --threads 2 --timeout 120`
4. **Environment Variables**:
   - `DJANGO_SETTINGS_MODULE`: `config.settings.production`
   - `SECRET_KEY`: `<generate-a-strong-secret-key>`
   - `DATABASE_URL`: `<Internal Connection String from Render PostgreSQL>`
   - `ALLOWED_HOSTS`: `.onrender.com,your-domain.com`
   - `CSRF_TRUSTED_ORIGINS`: `https://*.onrender.com,https://your-domain.com`
   - `SECURE_SSL_REDIRECT`: `true`
   - `ADMIN_EMAIL`: `admin@nawi.local`
   - `ADMIN_PASSWORD`: `<your-admin-password>`
5. **Disk**:
   - Name: `nawi-media`
   - Mount Path: `/var/data/media`
   - Size: 10 GB

---

## Database Backups

### Automated PostgreSQL Backup Script

NTRMS includes an automated backup script in [`scripts/backup_database.py`](file:///d:/NAWI%20Project/scripts/backup_database.py). It reads `DATABASE_URL` and creates timestamped gzip-compressed SQL dumps in `backups/`:

```bash
python scripts/backup_database.py
```

Output:
```text
[20261111_222019] Successfully created compressed backup: backups/nawi_db_backup_20261111_222019.sql.gz
```

### Automated Daily Cron Job (Linux / Render Cron)

Add to crontab (`crontab -e`):

```bash
0 2 * * * cd /path/to/nawi-project && /path/to/venv/bin/python scripts/backup_database.py >> /var/log/nawi_backup.log 2>&1
```

---

## Administrator Account Setup

To bootstrap an administrator account in any environment, run:

```bash
python scripts/create_production_admin.py
```

By default, the script reads:
- `ADMIN_EMAIL` (default: `admin@nawi.local`)
- `ADMIN_PASSWORD` (default: `Admin@12345`)
- `ADMIN_USERNAME` (default: `admin`)
- `ADMIN_ORG` (default: `National Metrology Testing Center`)

To create an account manually with Django's prompt:

```bash
python manage.py createsuperuser
```

---

## Running the Test Suite

The test suite contains **128 automated unit, integration, metrological calculation, and security tests**.

### Run Complete Test Suite

```bash
python manage.py test tests apps.instruments apps.measurements apps.test_sessions calculations apps.reports apps.accounts apps.audit apps.dashboard
```

### Run End-to-End Audit & Metrological Test Suite Only

```bash
python manage.py test tests.test_audit
```

Expected output:
```text
Ran 128 tests in 296.146s

OK
Destroying test database for alias 'default'...
Found 128 test(s).
System check identified no issues (0 silenced).
```

