# app.py
import os
import json
import logging
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, send_file
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit
from flask_mail import Message
from apscheduler.schedulers.background import BackgroundScheduler
import threading
from io import BytesIO

from config import config
from database import db, create_default_data, User, Machine, Alert, Appointment, TelemetryLog, Vendor, MaintenanceRecord, SystemLog, KPIMetric, AnalysisTask, EmailLog, MACHINE_CONFIG
from ml_models import MLModelManager
from telemetry_simulator import TelemetrySimulator
from agent import MaintenanceAgent
from email_service import EmailService, mail
from vendor_api import VendorAPI
from cost_calculator import CostCalculator
from scheduler_service import SchedulerService

# Create directories
os.makedirs('logs', exist_ok=True)
os.makedirs('models', exist_ok=True)
os.makedirs('data', exist_ok=True)
os.makedirs('reports', exist_ok=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/system.log'),
        logging.StreamHandler()
    ]
)

# Create Flask app
app = Flask(__name__)
app.config.from_object(config['default'])

# Initialize extensions
db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Initialize services
email_service = EmailService()
email_service.init_app(app)
email_service.enabled = True  # ENABLE EMAILS

vendor_api = VendorAPI()
cost_calculator = CostCalculator()

# Initialize ML models
ml_manager = MLModelManager()

# Initialize telemetry simulator
data_path = 'data/Medical_Equipment_Health_Dataset.csv'
telemetry_simulator = TelemetrySimulator(data_path=data_path if os.path.exists(data_path) else None)

# Global variables
agent = None
scheduler_service = None
analysis_in_progress = {}


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def log_system_event(log_type, source, message, details=None):
    """Log system events"""
    try:
        log = SystemLog(
            log_type=log_type,
            source=source,
            message=message,
            details=json.dumps(details) if details else None
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        logging.error(f"Failed to log event: {e}")


def get_status_display(status):
    """Get display properties for status"""
    displays = {
        'normal': {'emoji': '🟢', 'label': 'Normal', 'color': '#28a745', 'badge': 'bg-success'},
        'monitor': {'emoji': '🟡', 'label': 'Monitor', 'color': '#ffc107', 'badge': 'bg-warning'},
        'schedule_maintenance': {'emoji': '🔴', 'label': 'Schedule Maintenance', 'color': '#dc3545', 'badge': 'bg-danger'},
        'critical': {'emoji': '⚫', 'label': 'Critical', 'color': '#212529', 'badge': 'bg-dark'}
    }
    return displays.get(status, displays['normal'])


def get_operation_mode_display(mode):
    """Get display for operation mode"""
    modes = {
        'normal': {'label': 'Normal', 'color': '#28a745', 'icon': '✓'},
        'limp': {'label': 'Limp Mode', 'color': '#fd7e14', 'icon': '⚠'},
        'standby': {'label': 'Standby', 'color': '#6c757d', 'icon': '⏸'}
    }
    return modes.get(mode, modes['normal'])


def get_energy_mode_display(mode):
    """Get display for energy mode"""
    modes = {
        'ready': {'label': 'Ready', 'color': '#28a745', 'icon': '⚡'},
        'eco': {'label': 'Eco Mode', 'color': '#17a2b8', 'icon': '🌿'},
        'deep_sleep': {'label': 'Deep Sleep', 'color': '#6c757d', 'icon': '💤'}
    }
    return modes.get(mode, modes['ready'])


def get_machine_health_score(machine_id, readings):
    """Calculate health score"""
    if not readings:
        return 100
    
    machine_type = 'MRI' if 'mri' in machine_id.lower() else 'CT'
    score = 100
    
    cooling = readings.get('Cooling_System_Performance', 100)
    if cooling < 80:
        score -= 25
    elif cooling < 87:
        score -= 12
    elif cooling < 92:
        score -= 5
    
    vibration = readings.get('Vibration_Level', 0)
    if vibration > 3.5:
        score -= 20
    elif vibration > 2.8:
        score -= 10
    elif vibration > 2.2:
        score -= 5
    
    gradient = readings.get('Gradient_Coil_Temp', 45)
    if gradient > 65:
        score -= 20
    elif gradient > 56:
        score -= 10
    elif gradient > 52:
        score -= 5
    
    comp = readings.get('Component_Temp', 35)
    if comp > 46:
        score -= 15
    elif comp > 42:
        score -= 5
    
    if machine_type == 'MRI':
        helium = readings.get('Helium_Level', 100)
        if helium < 75:
            score -= 30
        elif helium < 82:
            score -= 15
        elif helium < 88:
            score -= 5
        
        magnet = readings.get('Magnet_Temp_K', 4.0)
        if magnet > 4.4:
            score -= 20
        elif magnet > 4.25:
            score -= 10
    else:
        tube = readings.get('X_ray_Tube_Temp', 50)
        if tube > 80:
            score -= 25
        elif tube > 72:
            score -= 12
        elif tube > 65:
            score -= 5
    
    return max(0, min(100, score))


def determine_machine_status(readings, health_score):
    """Determine machine status"""
    if not readings:
        return 'normal'
    
    severity = readings.get('Severity_Level', 0)
    
    if severity >= 5 or health_score < 40:
        return 'critical'
    elif severity >= 3 or health_score < 65:
        return 'schedule_maintenance'
    elif health_score < 82:
        return 'monitor'
    else:
        return 'normal'


def schedule_vendor_maintenance(machine, alert, predicted_days=None):
    """Schedule vendor maintenance and notify everyone"""
    severity = alert.severity
    
    # Determine schedule date
    if severity == 'critical':
        scheduled_date = datetime.now() + timedelta(hours=4)
        maintenance_type = 'emergency'
    else:
        # schedule BEFORE predicted failure day (buffer)
        if predicted_days and predicted_days > 1:
            scheduled_date = datetime.now() + timedelta(days=max(1, predicted_days - 2))
        else:
            scheduled_date = datetime.now() + timedelta(days=3)
        maintenance_type = 'scheduled'
    
    # Find vendor
    if machine.machine_type == 'MRI':
        vendor = Vendor.query.filter(Vendor.specialization.in_(['MRI', 'Both'])).first()
    else:
        vendor = Vendor.query.filter(Vendor.specialization.in_(['CT', 'Both'])).first()
    
    if not vendor:
        logging.error(f"No vendor found for {machine.machine_id}")
        return None

    # If already scheduled, allow escalation / earlier reschedule
    existing = None
    if machine.maintenance_scheduled:
        existing = MaintenanceRecord.query.filter(
            MaintenanceRecord.machine_id == machine.id,
            ~MaintenanceRecord.status.in_(['completed', 'cancelled'])
        ).order_by(MaintenanceRecord.scheduled_date.desc()).first()
    
    if existing:
        needs_reschedule = False
        if severity == 'critical' and existing.maintenance_type != 'emergency':
            needs_reschedule = True
        if existing.scheduled_date and scheduled_date and scheduled_date < existing.scheduled_date:
            needs_reschedule = True
        
        if not needs_reschedule:
            logging.info(f"Maintenance already scheduled for {machine.machine_id} on {existing.scheduled_date}")
            return existing
        
        existing.maintenance_type = maintenance_type
        existing.scheduled_date = scheduled_date
        existing.vendor_id = vendor.id
        existing.fault_summary = alert.description
        
        machine.scheduled_maintenance_date = scheduled_date
        machine.maintenance_scheduled = True
        machine.operation_mode = 'standby' if severity == 'critical' else 'limp'
        
        alert.vendor_contacted = True
        alert.vendor_scheduled_date = scheduled_date
        
        db.session.commit()
        
        # Keep alerts consistent: update any open alerts to show latest scheduled date
        try:
            open_alerts = Alert.query.filter(
                Alert.machine_id == machine.id,
                Alert.is_resolved == False
            ).all()
            for a in open_alerts:
                a.vendor_contacted = True
                a.vendor_scheduled_date = scheduled_date
            db.session.commit()
        except Exception:
            db.session.rollback()
        
        # Reschedule affected appointments on the (new) maintenance day
        rescheduled_count = reschedule_affected_appointments(machine, scheduled_date, existing)
        existing.patients_rescheduled = (existing.patients_rescheduled or 0) + rescheduled_count
        db.session.commit()
        
        # Notify again on escalation/reschedule
        send_maintenance_notifications(machine, alert, existing, vendor, scheduled_date)
        
        logging.info(f"Maintenance rescheduled for {machine.machine_id} on {scheduled_date}")
        return existing
    
    # Calculate cost
    base_hours = 6 if maintenance_type == 'emergency' else 4
    rate = vendor.hourly_rate or 250
    if maintenance_type == 'emergency':
        rate *= vendor.emergency_multiplier or 1.5
    estimated_cost = round(base_hours * rate, 2)
    
    # Create maintenance record
    maintenance = MaintenanceRecord(
        machine_id=machine.id,
        vendor_id=vendor.id,
        alert_id=alert.id,
        maintenance_type=maintenance_type,
        status='scheduled',
        scheduled_date=scheduled_date,
        fault_summary=alert.description,
        estimated_cost=estimated_cost
    )
    db.session.add(maintenance)
    
    # Update machine
    machine.maintenance_scheduled = True
    machine.scheduled_maintenance_date = scheduled_date
    if severity == 'critical':
        machine.operation_mode = 'standby'
    else:
        machine.operation_mode = 'limp'
    
    # Update alert
    alert.vendor_contacted = True
    alert.vendor_scheduled_date = scheduled_date
    
    db.session.commit()
    
    # Keep alerts consistent: update any open alerts to show latest scheduled date
    try:
        open_alerts = Alert.query.filter(
            Alert.machine_id == machine.id,
            Alert.is_resolved == False
        ).all()
        for a in open_alerts:
            a.vendor_contacted = True
            a.vendor_scheduled_date = scheduled_date
        db.session.commit()
    except Exception:
        db.session.rollback()
    
    # Reschedule affected appointments
    rescheduled_count = reschedule_affected_appointments(machine, scheduled_date, maintenance)
    maintenance.patients_rescheduled = rescheduled_count
    db.session.commit()
    
    # Send notifications to ALL stakeholders
    send_maintenance_notifications(machine, alert, maintenance, vendor, scheduled_date)
    
    logging.info(f"Maintenance scheduled for {machine.machine_id} on {scheduled_date}")
    
    return maintenance


def reschedule_affected_appointments(machine, maintenance_date, maintenance_record):
    """Reschedule appointments on maintenance date"""
    
    # Reschedule all appointments on the maintenance DATE (full day),
    # not just a fixed 8–17 window (prevents missing early/late appointments).
    maintenance_start = maintenance_date.replace(hour=0, minute=0, second=0, microsecond=0)
    maintenance_end = maintenance_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    # Find appointments on maintenance date
    affected = Appointment.query.filter(
        Appointment.machine_id == machine.id,
        Appointment.scheduled_datetime >= maintenance_start,
        Appointment.scheduled_datetime <= maintenance_end,
        Appointment.status.in_(['scheduled', 'confirmed'])
    ).all()
    
    rescheduled_count = 0
    
    for apt in affected:
        # Find next available day (skip weekends)
        new_date = apt.scheduled_datetime + timedelta(days=1)
        while new_date.weekday() >= 5:  # Skip weekends
            new_date += timedelta(days=1)
        
        # Store original
        apt.original_datetime = apt.scheduled_datetime
        apt.scheduled_datetime = new_date
        apt.status = 'rescheduled'
        apt.rescheduled_reason = f"Equipment maintenance: {maintenance_record.fault_summary[:80] if maintenance_record.fault_summary else 'Scheduled maintenance'}"
        apt.notification_sent = True
        apt.notification_sent_at = datetime.utcnow()
        
        # Send patient notification
        if email_service.enabled and apt.patient_email:
            email_service.send_patient_reschedule_notification(
                patient_email=apt.patient_email,
                patient_name=apt.patient_name,
                old_datetime=apt.original_datetime,
                new_datetime=new_date,
                reason=apt.rescheduled_reason,
                machine_id=machine.machine_id
            )
        
        rescheduled_count += 1
    
    db.session.commit()
    logging.info(f"Rescheduled {rescheduled_count} appointments for {machine.machine_id}")
    
    return rescheduled_count


def send_maintenance_notifications(machine, alert, maintenance, vendor, scheduled_date):
    """Send notifications to admin, engineer, radiologist, and vendor"""
    
    # Always send (user request). We still log each send for audit.
    
    # Log email
    email_log = EmailLog(
        machine_id=machine.machine_id,
        email_type='maintenance_scheduled',
        severity=alert.severity,
        recipients='all_staff_and_vendor',
        subject=f"Maintenance Scheduled - {machine.machine_id}"
    )
    db.session.add(email_log)
    db.session.commit()
    
    # Get all users
    users = User.query.filter(User.role.in_(['admin', 'engineer', 'radiologist'])).all()
    
    # Send to staff
    for user in users:
        if email_service.enabled:
            email_service.send_maintenance_scheduled_notification(
                recipient_email=user.email,
                recipient_name=user.full_name or user.username,
                machine=machine,
                alert=alert,
                scheduled_date=scheduled_date,
                vendor=vendor
            )
        logging.info(f"Notification sent to {user.email}")
    
    # Send to vendor
    if email_service.enabled:
        email_service.send_vendor_maintenance_request(
            vendor=vendor,
            machine=machine,
            alert=alert,
            scheduled_date=scheduled_date,
            maintenance_type=maintenance.maintenance_type
        )
    logging.info(f"Vendor notification sent to {vendor.contact_email}")
    
    # Send SMS (SMTP gateway) to staff + vendor
    try:
        send_maintenance_sms_notifications(machine, alert, maintenance, vendor, scheduled_date)
    except Exception as e:
        logging.error(f"Failed to send SMS maintenance notifications: {e}")
    
    maintenance.notifications_sent = True
    db.session.commit()


def send_vendor_sms_notification(vendor, machine, maintenance, fault_summary):
    """Send SMS alert to vendor via SMTP (email-to-SMS gateway) when manually contacted.
    
    - If `SMS_GATEWAY_DOMAIN` is configured, sends to: <digits_only_phone>@<gateway_domain>
    - Otherwise (optional), falls back to sending an email to vendor.contact_email
    """
    phone_number = getattr(vendor, "contact_phone", None) or ""
    digits_only = "".join([c for c in str(phone_number) if c.isdigit()])
    
    message_body = (
        f"Maintenance request for {machine.machine_id} "
        f"({machine.machine_type}) at {machine.location}. "
        f"Issue: {fault_summary}. "
        f"Scheduled on {maintenance.scheduled_date.strftime('%Y-%m-%d %H:%M')}."
    )
    
    sms_gateway = app.config.get("SMS_GATEWAY_DOMAIN")
    fallback_to_email = app.config.get("SMS_FALLBACK_TO_VENDOR_EMAIL", True)
    
    sms_recipient = None
    if sms_gateway and digits_only:
        sms_recipient = f"{digits_only}@{sms_gateway}"
    elif sms_gateway and not digits_only:
        logging.warning(
            f"SMS gateway configured but vendor phone is missing/invalid for vendor {getattr(vendor, 'name', 'UNKNOWN')}"
        )
    
    email_recipient = getattr(vendor, "contact_email", None)
    
    if not sms_recipient and not (fallback_to_email and email_recipient):
        logging.info(
            f"SMS not sent (no gateway/phone). Would notify vendor via SMS/email. Message: {message_body}"
        )
        return False
    
    try:
        recipients = [sms_recipient] if sms_recipient else [email_recipient]
        msg = Message(
            subject="PM Alert",
            recipients=recipients,
            body=message_body
        )
        with app.app_context():
            mail.send(msg)
        logging.info(f"Vendor alert sent via SMTP to {recipients[0]} for machine {machine.machine_id}")
        return True
    except Exception as e:
        logging.error(f"Failed to send vendor alert via SMTP: {e}")
        return False


def _sms_recipient_from_phone(phone_number):
    sms_gateway = app.config.get("SMS_GATEWAY_DOMAIN")
    if not sms_gateway:
        return None
    digits_only = "".join([c for c in str(phone_number or "") if c.isdigit()])
    if not digits_only:
        return None
    return f"{digits_only}@{sms_gateway}"


def send_sms_via_smtp(phone_number, message_body):
    """Send SMS via SMTP using an email-to-SMS gateway. Returns True if sent."""
    recipient = _sms_recipient_from_phone(phone_number)
    if not recipient:
        return False
    try:
        msg = Message(subject="PM Alert", recipients=[recipient], body=message_body)
        with app.app_context():
            mail.send(msg)
        logging.info(f"SMS sent via SMTP to {recipient}")
        return True
    except Exception as e:
        logging.error(f"Failed to send SMS via SMTP to {recipient}: {e}")
        return False


def send_maintenance_sms_notifications(machine, alert, maintenance, vendor, scheduled_date):
    """Auto-mode: SMS admin/engineer/radiologist/vendor when maintenance is scheduled."""
    if not EmailLog.can_send_email(machine.machine_id, 'sms_maintenance_scheduled', alert.severity, cooldown_minutes=60):
        logging.info(f"SMS maintenance notification already sent for {machine.machine_id}")
        return
    
    if not app.config.get("SMS_GATEWAY_DOMAIN"):
        logging.info("SMS_GATEWAY_DOMAIN not set; skipping auto SMS notifications")
        return
    
    body = (
        f"Maintenance scheduled: {machine.machine_id} ({machine.machine_type}) "
        f"{alert.severity.upper()}. "
        f"When {scheduled_date.strftime('%Y-%m-%d %H:%M')}. "
        f"Vendor {vendor.name}. "
        f"Issue: {alert.description}"
    )
    
    recipients_sent = []
    
    users = User.query.filter(User.role.in_(['admin', 'engineer', 'radiologist'])).all()
    for user in users:
        if user.phone and send_sms_via_smtp(user.phone, body):
            recipients_sent.append(user.phone)
    
    if getattr(vendor, "contact_phone", None) and send_sms_via_smtp(vendor.contact_phone, body):
        recipients_sent.append(vendor.contact_phone)
    
    if recipients_sent:
        sms_log = EmailLog(
            machine_id=machine.machine_id,
            email_type='sms_maintenance_scheduled',
            severity=alert.severity,
            recipients=json.dumps(recipients_sent),
            subject=f"SMS Maintenance Scheduled - {machine.machine_id}"
        )
        db.session.add(sms_log)
        db.session.commit()


@app.route('/api/admin/alerts/clear', methods=['POST'])
@login_required
def api_admin_clear_alerts():
    """Admin: clear alerts and related scheduling state."""
    if current_user.role != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        # Clear alerts and logs
        Alert.query.delete()
        EmailLog.query.delete()
        
        # Clear maintenance records
        MaintenanceRecord.query.delete()
        
        # Reset machines scheduling flags
        for machine in Machine.query.all():
            machine.maintenance_scheduled = False
            machine.scheduled_maintenance_date = None
            if machine.status != 'normal':
                machine.status = 'normal'
            if machine.operation_mode != 'normal':
                machine.operation_mode = 'normal'
            if machine.energy_mode != 'ready':
                machine.energy_mode = 'ready'
        
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/machines/reset-all', methods=['POST'])
@login_required
def api_admin_reset_all_machines():
    """Admin: reset all machines to normal and reset simulator degradation."""
    if current_user.role != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        machines = Machine.query.all()
        for machine in machines:
            machine.status = 'normal'
            machine.operation_mode = 'normal'
            machine.energy_mode = 'ready'
            machine.maintenance_scheduled = False
            machine.scheduled_maintenance_date = None
            machine.last_maintenance = datetime.utcnow()
            try:
                telemetry_simulator.reset_degradation(machine.machine_id)
            except Exception:
                pass
        
        # Resolve any leftover alerts
        for alert in Alert.query.filter(Alert.is_resolved == False).all():
            alert.is_resolved = True
            alert.resolved_at = datetime.utcnow()
            alert.resolved_by = current_user.id
            alert.resolution_notes = 'Reset all machines'
        
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/models/retrain', methods=['POST'])
@login_required
def api_admin_retrain_models():
    """Admin: retrain/reload ML models from dataset (best-effort)."""
    if current_user.role != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        if os.path.exists(data_path):
            ml_manager.initialize(data_path)
            return jsonify({'success': True})
        return jsonify({'error': f'Dataset not found at {data_path}'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/phones/bootstrap', methods=['POST'])
@login_required
def api_admin_bootstrap_phones():
    """Admin: set default phone numbers for SMS testing if missing."""
    if current_user.role != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    try:
        defaults = {
            'admin': '+917000000001',
            'engineer': '+917000000002',
            'radiologist': '+917000000003',
        }
        updated = 0
        for username, phone in defaults.items():
            user = User.query.filter_by(username=username).first()
            if user and not user.phone:
                user.phone = phone
                updated += 1
        
        # Vendors
        v1 = Vendor.query.filter_by(vendor_id='VENDOR-001').first()
        if v1 and not v1.contact_phone:
            v1.contact_phone = '+917094753374'
            updated += 1
        v2 = Vendor.query.filter_by(vendor_id='VENDOR-002').first()
        if v2 and not v2.contact_phone:
            v2.contact_phone = '+919962755810'
            updated += 1
        
        db.session.commit()
        return jsonify({'success': True, 'updated': updated})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/vendors/<vendor_id>/phone', methods=['POST'])
@login_required
def api_admin_update_vendor_phone(vendor_id):
    """Admin: update vendor contact_phone (supports Indian numbers)."""
    if current_user.role != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    data = request.get_json() or {}
    phone = (data.get('phone') or '').strip()
    if not phone:
        return jsonify({'error': 'phone is required'}), 400
    try:
        vendor = Vendor.query.filter_by(vendor_id=vendor_id).first()
        if not vendor:
            return jsonify({'error': 'Vendor not found'}), 404
        vendor.contact_phone = phone
        db.session.commit()
        return jsonify({'success': True, 'vendor_id': vendor_id, 'contact_phone': vendor.contact_phone})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

def create_auto_alert(machine, readings, status, health_score, predicted_days=None):
    """Create alert and schedule maintenance"""
    
    # Check for existing unresolved alert
    existing = Alert.query.filter(
        Alert.machine_id == machine.id,
        Alert.severity == status,
        Alert.is_resolved == False
    ).first()
    
    if existing:
        return existing
    
    # Check email cooldown
    if not EmailLog.can_send_email(machine.machine_id, 'alert', status, cooldown_minutes=30):
        return None
    
    # Build description
    issues = []
    machine_type = machine.machine_type
    
    cooling = readings.get('Cooling_System_Performance', 100)
    if cooling < 90:
        issues.append(f"Cooling: {cooling:.1f}%")
    
    vibration = readings.get('Vibration_Level', 0)
    if vibration > 2.2:
        issues.append(f"Vibration: {vibration:.2f} mm/s")
    
    gradient = readings.get('Gradient_Coil_Temp', 0)
    if gradient > 52:
        issues.append(f"Gradient Coil: {gradient:.1f}°C")
    
    if machine_type == 'MRI':
        helium = readings.get('Helium_Level', 100)
        if helium < 90:
            issues.append(f"Helium: {helium:.1f}%")
        magnet = readings.get('Magnet_Temp_K', 4.0)
        if magnet > 4.2:
            issues.append(f"Magnet: {magnet:.2f}K")
    else:
        tube = readings.get('X_ray_Tube_Temp', 0)
        if tube > 62:
            issues.append(f"X-ray Tube: {tube:.1f}°C")
    
    description = '; '.join(issues) if issues else 'Multiple parameters degraded'
    
    # Cost analysis
    cost_analysis = cost_calculator.calculate_cost_impact(machine_type, status, description)
    
    # Predicted failure date
    if status == 'critical':
        predicted_days = 1
        predicted_failure = datetime.now() + timedelta(days=1)
    elif status == 'schedule_maintenance':
        # Keep this conservative; if we flag maintenance now, failure is likely soon.
        predicted_days = predicted_days or 3
        predicted_failure = datetime.now() + timedelta(days=predicted_days)
    else:
        predicted_failure = None
    
    # Create alert
    status_labels = {
        'critical': '⚫ CRITICAL',
        'schedule_maintenance': '🔴 Maintenance Required',
        'monitor': '🟡 Monitoring'
    }
    
    alert = Alert(
        machine_id=machine.id,
        alert_type='auto_detection',
        severity=status,
        title=f"{status_labels.get(status, 'Alert')} - {machine.machine_id}",
        description=description,
        confidence_level=92.0,
        recommended_action=f"Health: {health_score}%. " + (
            "IMMEDIATE ACTION REQUIRED - Emergency maintenance scheduled." if status == 'critical'
            else f"Schedule maintenance before {predicted_failure.strftime('%Y-%m-%d') if predicted_failure else 'failure'}."
        ),
        estimated_prevention_cost=cost_analysis['prevention_cost'],
        estimated_breakdown_cost=cost_analysis['breakdown_cost'],
        predicted_failure_date=predicted_failure
    )
    
    db.session.add(alert)
    db.session.commit()
    
    # Log email
    email_log = EmailLog(
        machine_id=machine.machine_id,
        email_type='alert',
        severity=status,
        recipients='all_staff',
        subject=alert.title
    )
    db.session.add(email_log)
    db.session.commit()
    
    logging.info(f"Alert created: {alert.title}")
    
    # Send alert emails
    send_alert_notifications(machine, alert, cost_analysis)
    
    # Schedule maintenance for critical/schedule_maintenance
    if status in ['critical', 'schedule_maintenance']:
        schedule_vendor_maintenance(machine, alert, predicted_days)
    
    # Socket event
    socketio.emit('alert_generated', {
        'machine_id': machine.machine_id,
        'title': alert.title,
        'severity': status
    })
    
    return alert


def send_alert_notifications(machine, alert, cost_analysis):
    """Send alert notifications to all staff"""
    users = User.query.filter(User.role.in_(['admin', 'engineer', 'radiologist'])).all()
    
    for user in users:
        if email_service.enabled:
            email_service.send_alert_notification(
                recipient_email=user.email,
                recipient_name=user.full_name or user.username,
                machine_id=machine.machine_id,
                alert=alert,
                cost_analysis=cost_analysis
            )


def calculate_kpis():
    """Calculate KPIs"""
    try:
        total_machines = Machine.query.count()
        active_alerts = Alert.query.filter_by(is_resolved=False).count()
        critical_alerts = Alert.query.filter_by(severity='critical', is_resolved=False).count()
        scheduled_maintenance = MaintenanceRecord.query.filter_by(status='scheduled').count()
        
        machines = Machine.query.all()
        total_uptime = 0
        for m in machines:
            if m.status in ['normal', 'monitor']:
                total_uptime += 100
            elif m.status == 'schedule_maintenance':
                total_uptime += 70
            else:
                total_uptime += 0
        
        avg_uptime = total_uptime / total_machines if total_machines > 0 else 100
        
        resolved_alerts = Alert.query.filter_by(is_resolved=True).count()
        estimated_savings = resolved_alerts * 5000
        
        return {
            'total_machines': total_machines,
            'pending_alerts': active_alerts,
            'critical_alerts': critical_alerts,
            'scheduled_maintenance': scheduled_maintenance,
            'avg_uptime': round(avg_uptime, 1),
            'savings': estimated_savings,
            'energy_saved_kwh': 12.5
        }
    except Exception as e:
        logging.error(f"Error calculating KPIs: {e}")
        return {'pending_alerts': 0, 'savings': 0, 'total_machines': 5}

@app.context_processor
def inject_now():
    return {'now': datetime.now()}

# ==================== ROUTES ====================

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            user.last_login = datetime.utcnow()
            db.session.commit()
            log_system_event('info', 'auth', f'User {username} logged in')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    log_system_event('info', 'auth', f'User {current_user.username} logged out')
    logout_user()
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    machines = Machine.query.all()
    return render_template('dashboard.html', user=current_user, machines=machines)


@app.route('/machine/<machine_id>')
@login_required
def machine_detail(machine_id):
    machine = Machine.query.filter_by(machine_id=machine_id).first_or_404()
    
    # Get scheduled maintenance
    maintenance = MaintenanceRecord.query.filter(
        MaintenanceRecord.machine_id == machine.id,
        MaintenanceRecord.status.in_(['scheduled', 'confirmed'])
    ).order_by(MaintenanceRecord.scheduled_date.desc()).first()
    
    # Get recent alerts
    alerts = Alert.query.filter_by(machine_id=machine.id).order_by(Alert.timestamp.desc()).limit(5).all()
    
    return render_template('machine_detail.html', 
                         machine=machine, 
                         user=current_user,
                         scheduled_maintenance=maintenance,
                         recent_alerts=alerts)


@app.route('/schedules')
@login_required
def schedules():
    machine_filter = request.args.get('machine')
    status_filter = request.args.get('status')
    
    # Get appointments
    apt_query = Appointment.query
    if machine_filter:
        machine = Machine.query.filter_by(machine_id=machine_filter).first()
        if machine:
            apt_query = apt_query.filter_by(machine_id=machine.id)
    if status_filter:
        apt_query = apt_query.filter_by(status=status_filter)
    
    appointments = apt_query.order_by(Appointment.scheduled_datetime).limit(100).all()
    
    # Get scheduled maintenance
    maintenance_records = MaintenanceRecord.query.filter(
        MaintenanceRecord.status.in_(['scheduled', 'confirmed', 'in_progress'])
    ).order_by(MaintenanceRecord.scheduled_date).all()
    
    machines = Machine.query.all()
    
    return render_template('schedules.html', 
                         user=current_user, 
                         appointments=appointments, 
                         machines=machines,
                         maintenance_records=maintenance_records,
                         today=datetime.now().strftime('%Y-%m-%d'))


@app.route('/alerts')
@login_required
def alerts():
    all_alerts = Alert.query.order_by(Alert.timestamp.desc()).limit(100).all()
    return render_template('alerts.html', user=current_user, alerts=all_alerts)


@app.route('/vendors')
@login_required
def vendors():
    all_vendors = Vendor.query.all()
    return render_template('vendors.html', vendors=all_vendors, user=current_user)


@app.route('/reports')
@login_required
def reports():
    machines = Machine.query.all()
    return render_template('reports.html', user=current_user, machines=machines)


@app.route('/settings')
@login_required
def settings():
    if current_user.role != 'admin':
        flash('Admin access required', 'error')
        return redirect(url_for('dashboard'))
    return render_template('settings.html', user=current_user)


# ==================== API ENDPOINTS ====================

@app.route('/api/dashboard/data')
@login_required
def api_dashboard_data():
    """Get dashboard data"""
    try:
        data = {
            'machines': [],
            'alerts': [],
            'kpis': {},
            'analysis_status': {},
            'timestamp': datetime.now().isoformat()
        }
        
        machines = Machine.query.all()
        for machine in machines:
            readings = telemetry_simulator.get_current_readings(machine.machine_id)
            health_score = get_machine_health_score(machine.machine_id, readings)
            new_status = determine_machine_status(readings, health_score)
            
            # Check for status worsening
            status_order = {'normal': 0, 'monitor': 1, 'schedule_maintenance': 2, 'critical': 3}
            current_level = status_order.get(machine.status, 0)
            new_level = status_order.get(new_status, 0)
            
            if new_level > current_level:
                create_auto_alert(machine, readings, new_status, health_score)

            # Enforce vendor scheduling for critical/schedule_maintenance every time,
            # even if an alert was created elsewhere or earlier scheduling was missed.
            if new_status in ['critical', 'schedule_maintenance']:
                try:
                    latest_open = Alert.query.filter(
                        Alert.machine_id == machine.id,
                        Alert.is_resolved == False,
                        Alert.severity.in_(['critical', 'schedule_maintenance'])
                    ).order_by(Alert.timestamp.desc()).first()
                    if latest_open and not latest_open.vendor_scheduled_date:
                        schedule_vendor_maintenance(machine, latest_open, predicted_days=None)
                except Exception as e:
                    logging.error(f"Enforce scheduling failed for {machine.machine_id}: {e}")
            
            if machine.status != new_status:
                machine.status = new_status
                db.session.commit()
            
            # Get modes
            operation_mode = machine.operation_mode or 'normal'
            energy_mode = machine.energy_mode or 'ready'
            
            if new_status == 'critical':
                operation_mode = 'standby'
            elif new_status == 'schedule_maintenance':
                operation_mode = 'limp'
            
            machine_data = {
                'id': machine.id,
                'machine_id': machine.machine_id,
                'machine_type': machine.machine_type,
                'model': machine.model,
                'scan_category': machine.scan_category,
                'location': machine.location,
                'status': new_status,
                'status_display': get_status_display(new_status),
                'operation_mode': operation_mode,
                'operation_display': get_operation_mode_display(operation_mode),
                'energy_mode': energy_mode,
                'energy_display': get_energy_mode_display(energy_mode),
                'readings': readings,
                'health_score': health_score,
                'maintenance_scheduled': machine.maintenance_scheduled,
                'scheduled_maintenance_date': machine.scheduled_maintenance_date.isoformat() if machine.scheduled_maintenance_date else None,
                'is_analyzing': machine.machine_id in analysis_in_progress
            }
            data['machines'].append(machine_data)
        
        # Get alerts
        recent_alerts = Alert.query.order_by(Alert.timestamp.desc()).limit(10).all()
        for alert in recent_alerts:
            alert_machine = Machine.query.get(alert.machine_id)
            data['alerts'].append({
                'id': alert.id,
                'machine_id': alert_machine.machine_id if alert_machine else 'Unknown',
                'severity': alert.severity,
                'title': alert.title,
                'description': alert.description or '',
                'timestamp': alert.timestamp.isoformat(),
                'is_acknowledged': alert.is_acknowledged,
                'is_resolved': alert.is_resolved,
                'vendor_contacted': alert.vendor_contacted,
                'vendor_scheduled_date': alert.vendor_scheduled_date.isoformat() if alert.vendor_scheduled_date else None
            })
        
        data['kpis'] = calculate_kpis()
        
        return jsonify(data)
    
    except Exception as e:
        logging.error(f"Dashboard error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/machine/<machine_id>/telemetry')
@login_required
def api_machine_telemetry(machine_id):
    """Get telemetry"""
    readings = telemetry_simulator.get_current_readings(machine_id)
    history = telemetry_simulator.get_telemetry_history(machine_id, hours=6)
    
    return jsonify({
        'machine_id': machine_id,
        'current': readings,
        'history': history[-50:] if history else [],
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/machine/<machine_id>/analyze', methods=['POST'])
@login_required
def api_analyze_machine(machine_id):
    """Run analysis"""
    try:
        if machine_id in analysis_in_progress:
            return jsonify({'status': 'already_running'})
        
        analysis_in_progress[machine_id] = True
        socketio.emit('analysis_started', {'machine_id': machine_id})
        
        def run_analysis():
            try:
                if agent:
                    result = agent.analyze_machine(machine_id)
                    
                    # Ensure vendor scheduling happens for agent-generated alerts too
                    try:
                        with app.app_context():
                            machine = Machine.query.filter_by(machine_id=machine_id).first()
                            if machine:
                                latest = Alert.query.filter(
                                    Alert.machine_id == machine.id,
                                    Alert.is_resolved == False,
                                    Alert.severity.in_(['critical', 'schedule_maintenance'])
                                ).order_by(Alert.timestamp.desc()).first()
                                if latest and not latest.vendor_scheduled_date:
                                    predicted = None
                                    try:
                                        predicted = result.get('risk_report', {}).get('predicted_days_to_failure')
                                    except Exception:
                                        predicted = None
                                    schedule_vendor_maintenance(machine, latest, predicted)
                    except Exception as e:
                        logging.error(f"Post-analysis scheduling failed: {e}")
                    
                    socketio.emit('analysis_complete', {'machine_id': machine_id, 'result': result})
            except Exception as e:
                logging.error(f"Analysis error: {e}")
                socketio.emit('analysis_error', {'machine_id': machine_id, 'error': str(e)})
            finally:
                if machine_id in analysis_in_progress:
                    del analysis_in_progress[machine_id]
        
        thread = threading.Thread(target=run_analysis)
        thread.start()
        
        return jsonify({'status': 'started'})
    
    except Exception as e:
        if machine_id in analysis_in_progress:
            del analysis_in_progress[machine_id]
        return jsonify({'error': str(e)}), 500


@app.route('/api/machine/<machine_id>/reset-maintenance', methods=['POST'])
@login_required
def api_reset_maintenance(machine_id):
    """Mark maintenance complete and reset machine"""
    try:
        machine = Machine.query.filter_by(machine_id=machine_id).first()
        if not machine:
            return jsonify({'error': 'Machine not found'}), 404
        
        # Update machine
        machine.status = 'normal'
        machine.operation_mode = 'normal'
        machine.energy_mode = 'ready'
        machine.maintenance_scheduled = False
        machine.scheduled_maintenance_date = None
        machine.last_maintenance = datetime.utcnow()
        
        # Complete maintenance record
        maintenance = MaintenanceRecord.query.filter(
            MaintenanceRecord.machine_id == machine.id,
            MaintenanceRecord.status.in_(['scheduled', 'confirmed', 'in_progress'])
        ).first()
        
        if maintenance:
            maintenance.status = 'completed'
            maintenance.completed_at = datetime.utcnow()
        
        # Resolve related alerts
        unresolved_alerts = Alert.query.filter(
            Alert.machine_id == machine.id,
            Alert.is_resolved == False
        ).all()
        
        for alert in unresolved_alerts:
            alert.is_resolved = True
            alert.resolved_at = datetime.utcnow()
            alert.resolved_by = current_user.id
            alert.resolution_notes = 'Maintenance completed'
        
        db.session.commit()
        
        # Reset telemetry simulator
        telemetry_simulator.reset_degradation(machine_id)
        
        # Reset agent state
        if agent and machine_id in agent.machine_states:
            from agent import RiskTier, OperationMode, EnergyMode
            agent.machine_states[machine_id]['status'] = RiskTier.NORMAL
            agent.machine_states[machine_id]['operation_mode'] = OperationMode.NORMAL
            agent.machine_states[machine_id]['energy_mode'] = EnergyMode.READY
            agent.machine_states[machine_id]['consecutive_anomalies'] = 0
        
        log_system_event('info', 'maintenance', f'Maintenance completed for {machine_id} by {current_user.username}')
        
        return jsonify({
            'success': True, 
            'message': 'Maintenance completed successfully',
            'machine_id': machine_id
        })
    
    except Exception as e:
        logging.error(f"Reset maintenance error: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/machine/<machine_id>/inject-fault', methods=['POST'])
@login_required
def api_inject_fault(machine_id):
    """Inject fault"""
    if current_user.role != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    
    data = request.get_json() or {}
    fault_type = data.get('fault_type', 'general')
    
    reading = telemetry_simulator.inject_fault(machine_id, fault_type)
    log_system_event('warning', 'testing', f'Fault injected: {fault_type} on {machine_id}')
    
    return jsonify({'success': True, 'message': f'Fault {fault_type} injected', 'reading': reading})


@app.route('/api/machine/<machine_id>/set-mode', methods=['POST'])
@login_required
def api_set_machine_mode(machine_id):
    """Set machine mode"""
    if current_user.role not in ['admin', 'engineer']:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json() or {}
    mode_type = data.get('mode_type')
    mode_value = data.get('mode_value')
    
    machine = Machine.query.filter_by(machine_id=machine_id).first()
    if not machine:
        return jsonify({'error': 'Machine not found'}), 404
    
    if mode_type == 'operation':
        machine.operation_mode = mode_value
    elif mode_type == 'energy':
        machine.energy_mode = mode_value
    
    db.session.commit()
    
    return jsonify({'success': True})


@app.route('/api/alerts/<int:alert_id>/acknowledge', methods=['POST'])
@login_required
def api_acknowledge_alert(alert_id):
    """Acknowledge alert"""
    alert = Alert.query.get_or_404(alert_id)
    alert.is_acknowledged = True
    alert.acknowledged_by = current_user.id
    alert.acknowledged_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({'success': True})


@app.route('/api/alerts/<int:alert_id>/resolve', methods=['POST'])
@login_required
def api_resolve_alert(alert_id):
    """Resolve alert"""
    data = request.get_json() or {}
    alert = Alert.query.get_or_404(alert_id)
    alert.is_resolved = True
    alert.resolved_by = current_user.id
    alert.resolved_at = datetime.utcnow()
    alert.resolution_notes = data.get('notes', 'Resolved')
    db.session.commit()
    
    return jsonify({'success': True})


@app.route('/api/alerts')
@login_required
def api_get_alerts():
    """Get alerts"""
    severity = request.args.get('severity')
    is_resolved = request.args.get('resolved')
    
    query = Alert.query
    if severity:
        query = query.filter_by(severity=severity)
    if is_resolved is not None:
        query = query.filter_by(is_resolved=is_resolved.lower() == 'true')
    
    alerts_list = query.order_by(Alert.timestamp.desc()).limit(100).all()
    
    result = []
    for alert in alerts_list:
        alert_machine = Machine.query.get(alert.machine_id)
        result.append({
            'id': alert.id,
            'machine_id': alert_machine.machine_id if alert_machine else 'Unknown',
            'severity': alert.severity,
            'title': alert.title,
            'description': alert.description or '',
            'timestamp': alert.timestamp.isoformat(),
            'is_acknowledged': alert.is_acknowledged,
            'is_resolved': alert.is_resolved,
            'vendor_contacted': alert.vendor_contacted,
            'vendor_scheduled_date': alert.vendor_scheduled_date.isoformat() if alert.vendor_scheduled_date else None
        })
    
    return jsonify({'alerts': result})


@app.route('/api/cost-analysis/<machine_id>')
@login_required
def api_cost_analysis(machine_id):
    """Get cost analysis"""
    machine = Machine.query.filter_by(machine_id=machine_id).first()
    if not machine:
        return jsonify({'error': 'Machine not found'}), 404
    
    analysis = cost_calculator.calculate_cost_impact(
        machine.machine_type, 
        machine.status or 'normal', 
        'Analysis'
    )
    analysis['machine_id'] = machine_id
    
    return jsonify(analysis)


@app.route('/api/schedules/reschedule', methods=['POST'])
@login_required
def api_reschedule_appointment():
    """Reschedule appointment"""
    data = request.get_json()
    appointment_id = data.get('appointment_id')
    new_datetime_str = data.get('new_datetime')
    reason = data.get('reason', 'Manual reschedule')
    
    try:
        apt = Appointment.query.filter_by(appointment_id=appointment_id).first()
        if not apt:
            return jsonify({'error': 'Appointment not found'}), 404
        
        new_datetime = datetime.fromisoformat(new_datetime_str)
        
        apt.original_datetime = apt.scheduled_datetime
        apt.scheduled_datetime = new_datetime
        apt.status = 'rescheduled'
        apt.rescheduled_reason = reason
        apt.notification_sent = True
        apt.notification_sent_at = datetime.utcnow()
        
        db.session.commit()
        
        # Send notification
        if email_service.enabled and apt.patient_email:
            email_service.send_patient_reschedule_notification(
                patient_email=apt.patient_email,
                patient_name=apt.patient_name,
                old_datetime=apt.original_datetime,
                new_datetime=new_datetime,
                reason=reason
            )
        
        return jsonify({'success': True})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/reports/generate', methods=['POST'])
@login_required
def api_generate_report():
    """Generate report"""
    data = request.get_json() or {}
    report_type = data.get('type', 'summary')
    
    try:
        if report_type == 'cost_analysis':
            report_data = {'total_prevention_cost': 0, 'total_breakdown_cost': 0, 'machines': []}
            for m in Machine.query.all():
                analysis = cost_calculator.calculate_cost_impact(m.machine_type, m.status or 'normal', 'Analysis')
                report_data['total_prevention_cost'] += analysis['prevention_cost']
                report_data['total_breakdown_cost'] += analysis['breakdown_cost']
                report_data['machines'].append({'machine_id': m.machine_id, **analysis})
            report_data['total_potential_savings'] = report_data['total_breakdown_cost'] - report_data['total_prevention_cost']
        else:
            report_data = {
                'kpis': calculate_kpis(),
                'machines': [{'machine_id': m.machine_id, 'status': m.status, 'type': m.machine_type} for m in Machine.query.all()],
                'generated_at': datetime.now().isoformat()
            }
        
        return jsonify({'success': True, 'report': report_data})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/reports/export/<report_type>')
@login_required
def api_export_report(report_type):
    """Export report"""
    try:
        report_data = {
            'title': f'{report_type.upper()} Report',
            'generated_at': datetime.now().isoformat(),
            'generated_by': current_user.username,
            'machines': []
        }
        
        for m in Machine.query.all():
            analysis = cost_calculator.calculate_cost_impact(m.machine_type, m.status or 'normal', 'Analysis')
            report_data['machines'].append({
                'machine_id': m.machine_id,
                'machine_type': m.machine_type,
                'status': m.status,
                **analysis
            })
        
        buffer = BytesIO()
        buffer.write(json.dumps(report_data, indent=2).encode())
        buffer.seek(0)
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f'{report_type}_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json',
            mimetype='application/json'
        )
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/vendor/contact', methods=['POST'])
@login_required
def api_contact_vendor():
    """Contact vendor"""
    data = request.get_json()
    machine_id = data.get('machine_id')
    fault_summary = data.get('fault_summary', 'Maintenance required')
    urgency = data.get('urgency', 'scheduled')
    
    try:
        machine = Machine.query.filter_by(machine_id=machine_id).first()
        if not machine:
            return jsonify({'error': 'Machine not found'}), 404
        
        # Find vendor
        if machine.machine_type == 'MRI':
            vendor = Vendor.query.filter(Vendor.specialization.in_(['MRI', 'Both'])).first()
        else:
            vendor = Vendor.query.filter(Vendor.specialization.in_(['CT', 'Both'])).first()
        
        if not vendor:
            return jsonify({'error': 'No vendor available'}), 404
        
        # Create maintenance record
        scheduled_date = datetime.now() + timedelta(days=1 if urgency == 'emergency' else 3)
        
        maintenance = MaintenanceRecord(
            machine_id=machine.id,
            vendor_id=vendor.id,
            maintenance_type=urgency,
            status='scheduled',
            scheduled_date=scheduled_date,
            fault_summary=fault_summary,
            estimated_cost=1500.00
        )
        
        db.session.add(maintenance)
        machine.maintenance_scheduled = True
        machine.scheduled_maintenance_date = scheduled_date
        db.session.commit()
        
        # Send SMS alert to vendor only when manually contacted
        send_vendor_sms_notification(vendor, machine, maintenance, fault_summary)
        
        return jsonify({
            'success': True,
            'vendor_name': vendor.name,
            'scheduled_date': scheduled_date.isoformat()
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== WEBSOCKET ====================

@socketio.on('connect')
def handle_connect():
    emit('connected', {'status': 'connected'})


@socketio.on('request_telemetry')
def handle_telemetry_request(data):
    machine_id = data.get('machine_id')
    if machine_id:
        readings = telemetry_simulator.get_current_readings(machine_id)
        emit('telemetry_update', {'machine_id': machine_id, 'readings': readings})


# ==================== BACKGROUND ====================

def telemetry_callback(machine_id, reading):
    """Telemetry callback"""
    try:
        socketio.emit('telemetry_update', {
            'machine_id': machine_id,
            'readings': reading,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        pass


def run_scheduled_analysis():
    """Scheduled analysis"""
    with app.app_context():
        for machine_id in telemetry_simulator.MACHINE_IDS:
            try:
                machine = Machine.query.filter_by(machine_id=machine_id).first()
                if machine:
                    readings = telemetry_simulator.get_current_readings(machine_id)
                    health_score = get_machine_health_score(machine_id, readings)
                    new_status = determine_machine_status(readings, health_score)
                    
                    status_order = {'normal': 0, 'monitor': 1, 'schedule_maintenance': 2, 'critical': 3}
                    if status_order.get(new_status, 0) > status_order.get(machine.status, 0):
                        create_auto_alert(machine, readings, new_status, health_score)
                    
                    if machine.status != new_status:
                        machine.status = new_status
                        db.session.commit()
            except Exception as e:
                logging.error(f"Scheduled analysis error: {e}")


# ==================== INIT ====================

def init_application():
    """Initialize application"""
    global agent, scheduler_service
    
    with app.app_context():
        db.create_all()
        create_default_data()
        
        if os.path.exists(data_path):
            ml_manager.initialize(data_path)
        
        scheduler_service = SchedulerService(db)
        
        agent = MaintenanceAgent(
            ml_manager=ml_manager,
            telemetry_simulator=telemetry_simulator,
            db=db,
            email_service=email_service,
            vendor_api=vendor_api
        )
        
        for machine_id in telemetry_simulator.MACHINE_IDS:
            if machine_id not in agent.machine_states:
                agent._initialize_machine_state(machine_id)
        
        if Appointment.query.count() == 0:
            for machine_id in telemetry_simulator.MACHINE_IDS:
                scheduler_service.generate_sample_appointments(machine_id)
        
        logging.info("Application initialized")


# ==================== MAIN ====================

if __name__ == '__main__':
    init_application()
    
    telemetry_simulator.register_callback(telemetry_callback)
    telemetry_simulator.start_simulation(interval_seconds=5)
    
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_scheduled_analysis, 'interval', minutes=1)
    scheduler.start()
    
    logging.info("=" * 50)
    logging.info("Starting Predictive Maintenance Agent")
    logging.info("Dashboard: http://localhost:5000")
    logging.info("Admin: admin / admin123")
    logging.info("=" * 50)
    
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, use_reloader=False)