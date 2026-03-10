# med-agent

## Glitchcon — Predictive Maintenance + Auto Vendor Scheduling

Glitchcon is a Flask-based predictive maintenance dashboard for medical imaging equipment (MRI/CT). It simulates telemetry, detects degraded conditions, generates alerts, auto-schedules vendor maintenance, reschedules affected patient appointments, and notifies stakeholders (admin/engineer/radiologist/vendor).

## Key Features

- **Live dashboard**
  - Real-time telemetry updates (Socket.IO)
  - Machine health/status display
  - Recent alerts feed and KPIs

- **Alerts**
  - Auto-generated alerts when status worsens
  - Alerts page with **Resolve** action (modal-based)

- **Auto vendor scheduling**
  - When machine status becomes **`schedule_maintenance`** or **`critical`**:
    - Vendor is auto-selected based on machine type (MRI/CT)
    - Maintenance record created (or updated if already scheduled)
    - Maintenance date escalates earlier if severity escalates to critical
  - Prevents “vendor not scheduled” by enforcing scheduling in dashboard refresh

- **Appointment rescheduling + patient email**
  - When maintenance is scheduled/rescheduled:
    - Appointments on the maintenance **date (full day)** are rescheduled
    - Patients are emailed the updated appointment details (SMTP via Flask-Mail)

- **Manual vendor contact**
  - “Contact Vendor” button triggers vendor contact workflow
  - Sends vendor alert via SMTP (see notes on SMS gateway limitations)

- **Admin actions**
  - Clear all alerts/maintenance records
  - Reset all machines
  - Retrain/reload ML models (best-effort)

## Tech Stack

- **Backend**: Python, Flask, Flask-Login, Flask-SQLAlchemy
- **Realtime**: Flask-SocketIO
- **Scheduling**: APScheduler
- **Email (SMTP)**: Flask-Mail
- **Frontend**: Bootstrap 5, Chart.js, vanilla JS

## How the System Works (High-level Flow)

1. Telemetry simulator produces readings for each machine.
2. Status is derived from readings:
   - `normal` → ok
   - `monitor` → mild degradation
   - `schedule_maintenance` → maintenance recommended soon
   - `critical` → immediate/emergency action
3. When status worsens, the system creates an alert.
4. For `schedule_maintenance`/`critical`, the system:
   - assigns a vendor
   - schedules maintenance
   - notifies stakeholders
   - reschedules patient appointments on maintenance date and emails patients
5. If the machine escalates from `schedule_maintenance` to `critical`,
   maintenance is **rescheduled earlier** and notifications are sent again.

## Important Implementations & Fixes Included

- **Bootstrap JS enabled globally**
  - Fixed non-working modals/actions (Resolve/Reschedule) by adding Bootstrap bundle JS in `templates/base.html`.

- **Critical escalation fix**
  - If maintenance was already scheduled for a later date, and later the machine becomes `critical`,
    the maintenance record is **updated/rescheduled earlier** (emergency).

- **“Not scheduled” prevention**
  - Vendor scheduling is enforced for any machine that is currently `critical` / `schedule_maintenance`
    during dashboard refresh. This prevents open alerts from showing “Not scheduled”.

- **Patient reschedule coverage**
  - Reschedule now considers the **entire maintenance date (00:00–23:59)** instead of only 08:00–17:00,
    preventing missed appointments and missing patient emails.

- **Email sending behavior**
  - Maintenance emails are sent to admin/engineer/radiologist/vendor (SMTP).
  - Cooldown suppression for maintenance notifications was removed to “always send” as requested.

- **Vendor phone updates from seed**
  - `database.py` seeding now updates existing vendor contact fields (including phone) so changes in
    `vendors_config` apply even if the vendor already exists in SQLite.

## Configuration

### SMTP (Email) Settings
Configured in `config.py`:

- `MAIL_SERVER`
- `MAIL_PORT`
- `MAIL_USE_TLS`
- `MAIL_USERNAME`
- `MAIL_PASSWORD`
- `MAIL_DEFAULT_SENDER`

### “SMS via SMTP gateway” (Email-to-SMS)
Set environment variable:

- `SMS_GATEWAY_DOMAIN`

The system sends to: `<digits_only_phone>@SMS_GATEWAY_DOMAIN`

> NOTE (India/Jio): Most Indian carriers (including Jio) do **not** provide a public email-to-SMS gateway.
> If you do not have a working gateway domain, SMTP will deliver as an **email**, not a real SMS.
> For true SMS to Indian numbers, use an SMS provider API.

Optional environment variable:

- `SMS_FALLBACK_TO_VENDOR_EMAIL` (default `true`)

## Run Locally

1. Create/activate a virtual environment (recommended)
2. Install dependencies (if you have a requirements file), then run:

```bash
python app.py
