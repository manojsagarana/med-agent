# database.py
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='engineer')
    full_name = db.Column(db.String(150))
    department = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Machine(db.Model):
    __tablename__ = 'machines'
    
    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.String(50), unique=True, nullable=False)
    machine_type = db.Column(db.String(20), nullable=False)
    model = db.Column(db.String(100))
    manufacturer = db.Column(db.String(100))
    scan_category = db.Column(db.String(50))
    installation_date = db.Column(db.Date)
    last_maintenance = db.Column(db.DateTime)
    location = db.Column(db.String(200))
    
    status = db.Column(db.String(20), default='normal')
    operation_mode = db.Column(db.String(20), default='normal')
    energy_mode = db.Column(db.String(20), default='ready')
    
    # Alert tracking - prevent duplicate emails
    last_alert_sent = db.Column(db.DateTime)
    last_alert_severity = db.Column(db.String(20))
    maintenance_scheduled = db.Column(db.Boolean, default=False)
    scheduled_maintenance_date = db.Column(db.DateTime)
    
    baseline_data = db.Column(db.Text)
    total_uptime_hours = db.Column(db.Float, default=0)
    total_scans = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    telemetry_logs = db.relationship('TelemetryLog', backref='machine', lazy='dynamic')
    alerts = db.relationship('Alert', backref='machine', lazy='dynamic')
    appointments = db.relationship('Appointment', backref='machine', lazy='dynamic')
    maintenance_records = db.relationship('MaintenanceRecord', backref='machine', lazy='dynamic')


class TelemetryLog(db.Model):
    __tablename__ = 'telemetry_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.Integer, db.ForeignKey('machines.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    component_temp = db.Column(db.Float)
    gradient_coil_temp = db.Column(db.Float)
    vibration_level = db.Column(db.Float)
    cooling_system_performance = db.Column(db.Float)
    error_code = db.Column(db.String(20))
    severity_level = db.Column(db.Integer, default=0)
    
    magnet_temp_k = db.Column(db.Float)
    helium_level = db.Column(db.Float)
    helium_pressure_psi = db.Column(db.Float)
    
    xray_tube_temp = db.Column(db.Float)
    cooling_oil_temp = db.Column(db.Float)
    
    scan_type = db.Column(db.String(50))
    scan_count = db.Column(db.Integer, default=0)


class Alert(db.Model):
    __tablename__ = 'alerts'
    
    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.Integer, db.ForeignKey('machines.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    alert_type = db.Column(db.String(50), nullable=False)
    severity = db.Column(db.String(20), nullable=False)
    
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    affected_parameters = db.Column(db.Text)
    confidence_level = db.Column(db.Float)
    
    recommended_action = db.Column(db.Text)
    estimated_prevention_cost = db.Column(db.Float)
    estimated_breakdown_cost = db.Column(db.Float)
    predicted_failure_date = db.Column(db.DateTime)
    
    # Email tracking
    email_sent = db.Column(db.Boolean, default=False)
    email_sent_at = db.Column(db.DateTime)
    email_recipients = db.Column(db.Text)  # JSON list
    
    # Vendor scheduling
    vendor_contacted = db.Column(db.Boolean, default=False)
    vendor_scheduled_date = db.Column(db.DateTime)
    
    is_acknowledged = db.Column(db.Boolean, default=False)
    acknowledged_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    acknowledged_at = db.Column(db.DateTime)
    
    is_resolved = db.Column(db.Boolean, default=False)
    resolved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    resolved_at = db.Column(db.DateTime)
    resolution_notes = db.Column(db.Text)


class Vendor(db.Model):
    __tablename__ = 'vendors'
    
    id = db.Column(db.Integer, primary_key=True)
    vendor_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    specialization = db.Column(db.String(100))
    contact_email = db.Column(db.String(120), nullable=False)
    contact_phone = db.Column(db.String(20))
    api_endpoint = db.Column(db.String(250))
    api_key = db.Column(db.String(100))
    
    hourly_rate = db.Column(db.Float)
    emergency_multiplier = db.Column(db.Float, default=1.5)
    availability_slots = db.Column(db.Text)
    
    is_active = db.Column(db.Boolean, default=True)
    rating = db.Column(db.Float, default=5.0)
    
    maintenance_records = db.relationship('MaintenanceRecord', backref='vendor', lazy='dynamic')


class MaintenanceRecord(db.Model):
    __tablename__ = 'maintenance_records'
    
    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.Integer, db.ForeignKey('machines.id'), nullable=False)
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendors.id'))
    alert_id = db.Column(db.Integer, db.ForeignKey('alerts.id'))
    
    maintenance_type = db.Column(db.String(50), nullable=False)  # emergency, scheduled, preventive
    status = db.Column(db.String(30), default='scheduled')  # scheduled, confirmed, in_progress, completed, cancelled
    
    scheduled_date = db.Column(db.DateTime)
    confirmed_date = db.Column(db.DateTime)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    
    fault_summary = db.Column(db.Text)
    work_performed = db.Column(db.Text)
    parts_replaced = db.Column(db.Text)
    
    estimated_cost = db.Column(db.Float)
    actual_cost = db.Column(db.Float)
    
    technician_name = db.Column(db.String(100))
    technician_notes = db.Column(db.Text)
    
    # Notification tracking
    notifications_sent = db.Column(db.Boolean, default=False)
    patients_rescheduled = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Appointment(db.Model):
    __tablename__ = 'appointments'
    
    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.String(50), unique=True, nullable=False)
    machine_id = db.Column(db.Integer, db.ForeignKey('machines.id'), nullable=False)
    
    patient_name = db.Column(db.String(150), nullable=False)
    patient_email = db.Column(db.String(120))
    patient_phone = db.Column(db.String(20))
    patient_id = db.Column(db.String(50))
    
    scan_type = db.Column(db.String(100), nullable=False)
    scan_duration_minutes = db.Column(db.Integer, default=30)
    priority = db.Column(db.String(20), default='normal')
    
    scheduled_datetime = db.Column(db.DateTime, nullable=False)
    original_datetime = db.Column(db.DateTime)
    
    status = db.Column(db.String(30), default='scheduled')
    
    notes = db.Column(db.Text)
    rescheduled_reason = db.Column(db.Text)
    notification_sent = db.Column(db.Boolean, default=False)
    notification_sent_at = db.Column(db.DateTime)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SystemLog(db.Model):
    __tablename__ = 'system_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    log_type = db.Column(db.String(50), nullable=False)
    source = db.Column(db.String(100))
    message = db.Column(db.Text, nullable=False)
    details = db.Column(db.Text)


class KPIMetric(db.Model):
    __tablename__ = 'kpi_metrics'
    
    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.Integer, db.ForeignKey('machines.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    
    uptime_percentage = db.Column(db.Float)
    scan_count = db.Column(db.Integer, default=0)
    energy_consumption_kwh = db.Column(db.Float)
    eco_mode_hours = db.Column(db.Float, default=0)
    limp_mode_hours = db.Column(db.Float, default=0)
    downtime_hours = db.Column(db.Float, default=0)
    
    anomalies_detected = db.Column(db.Integer, default=0)
    alerts_generated = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AnalysisTask(db.Model):
    __tablename__ = 'analysis_tasks'
    
    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.String(50), nullable=False)
    task_type = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='running')
    progress = db.Column(db.Integer, default=0)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    result = db.Column(db.Text)
    error_message = db.Column(db.Text)


# Email log to prevent duplicates
class EmailLog(db.Model):
    __tablename__ = 'email_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.String(50), nullable=False)
    email_type = db.Column(db.String(50), nullable=False)  # alert, maintenance, reschedule
    severity = db.Column(db.String(20))
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    recipients = db.Column(db.Text)
    subject = db.Column(db.String(200))
    
    # Prevent duplicate emails
    @staticmethod
    def can_send_email(machine_id, email_type, severity, cooldown_minutes=30):
        """Check if email can be sent (not duplicate within cooldown period)"""
        from datetime import timedelta
        cutoff_time = datetime.utcnow() - timedelta(minutes=cooldown_minutes)
        
        recent = EmailLog.query.filter(
            EmailLog.machine_id == machine_id,
            EmailLog.email_type == email_type,
            EmailLog.severity == severity,
            EmailLog.sent_at > cutoff_time
        ).first()
        
        return recent is None


# All 5 machines configuration
MACHINE_CONFIG = [
    {
        'machine_id': 'mri_brain_01',
        'machine_type': 'MRI',
        'model': 'Siemens MAGNETOM Vida 3T',
        'manufacturer': 'Siemens Healthineers',
        'scan_category': 'brain',
        'location': 'Radiology Department - Room 101'
    },
    {
        'machine_id': 'mri_spine_01',
        'machine_type': 'MRI',
        'model': 'GE SIGNA Premier 3T',
        'manufacturer': 'GE Healthcare',
        'scan_category': 'spine',
        'location': 'Radiology Department - Room 102'
    },
    {
        'machine_id': 'mri_msk_01',
        'machine_type': 'MRI',
        'model': 'Philips Ingenia Elition 3T',
        'manufacturer': 'Philips Healthcare',
        'scan_category': 'msk',
        'location': 'Radiology Department - Room 103'
    },
    {
        'machine_id': 'ct_chest_01',
        'machine_type': 'CT',
        'model': 'Siemens SOMATOM Force',
        'manufacturer': 'Siemens Healthineers',
        'scan_category': 'chest',
        'location': 'Radiology Department - Room 201'
    },
    {
        'machine_id': 'ct_abdo_01',
        'machine_type': 'CT',
        'model': 'GE Revolution CT',
        'manufacturer': 'GE Healthcare',
        'scan_category': 'abdo',
        'location': 'Radiology Department - Room 202'
    }
]


def create_default_data():
    """Create default data (users, machines, vendors)"""
    
    users_config = [
        {
            'username': 'admin',
            'email': 'manojsagaran0412@gmail.com',
            'role': 'admin',
            'full_name': 'System Administrator',
            'department': 'IT',
            'phone': '+917000000001',
            'password': 'admin123'
        },
        {
            'username': 'engineer',
            'email': 'manojsagaran0412@gmail.com',
            'role': 'engineer',
            'full_name': 'Hospital Engineer',
            'department': 'Engineering',
            'phone': '+917000000002',
            'password': 'engineer123'
        },
        {
            'username': 'radiologist',
            'email': 'manojsagaran0412@gmail.com',
            'role': 'radiologist',
            'full_name': 'Head of Radiology',
            'department': 'Radiology',
            'phone': '+917000000003',
            'password': 'radio123'
        }
    ]
    
    for user_config in users_config:
        try:
            existing_user = User.query.filter_by(username=user_config['username']).first()
            if existing_user:
                continue
            
            existing_email = User.query.filter_by(email=user_config['email']).first()
            if existing_email:
                user_config['email'] = f"{user_config['username']}_{datetime.now().strftime('%H%M%S')}@hospital.com"
            
            user = User(
                username=user_config['username'],
                email=user_config['email'],
                role=user_config['role'],
                full_name=user_config['full_name'],
                department=user_config['department'],
                phone=user_config.get('phone')
            )
            user.set_password(user_config['password'])
            db.session.add(user)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Error creating user {user_config['username']}: {e}")
    
    for machine_config in MACHINE_CONFIG:
        try:
            if not Machine.query.filter_by(machine_id=machine_config['machine_id']).first():
                machine = Machine(**machine_config)
                db.session.add(machine)
                db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Error creating machine {machine_config['machine_id']}: {e}")
    
    vendors_config = [
        {
            'vendor_id': 'VENDOR-001',
            'name': 'MedTech Service Solutions',
            'specialization': 'Both',
            'contact_email': 'manojsagaran2004@gmail.com',
            'contact_phone': '+91 7094753374',
            'hourly_rate': 250.00,
            'api_endpoint': 'https://api.medtechsolutions.com/service',
            'availability_slots': '{"monday": ["09:00-17:00"], "tuesday": ["09:00-17:00"], "wednesday": ["09:00-17:00"], "thursday": ["09:00-17:00"], "friday": ["09:00-17:00"]}'
        },
        {
            'vendor_id': 'VENDOR-002',
            'name': 'Imaging Equipment Experts',
            'specialization': 'MRI',
            'contact_email': 'giridharansivakumar92@gmail.com',
            'contact_phone': '+91 9962755810',
            'hourly_rate': 280.00,
            'emergency_multiplier': 2.0,
            'api_endpoint': 'https://api.imagingexperts.com/service',
            'availability_slots': '{"monday": ["08:00-18:00"], "tuesday": ["08:00-18:00"], "wednesday": ["08:00-18:00"], "thursday": ["08:00-18:00"], "friday": ["08:00-18:00"], "saturday": ["10:00-14:00"]}'
        }
    ]
    
    for vendor_config in vendors_config:
        try:
            existing_vendor = Vendor.query.filter_by(vendor_id=vendor_config['vendor_id']).first()
            if not existing_vendor:
                vendor = Vendor(**vendor_config)
                db.session.add(vendor)
                db.session.commit()
            else:
                # Keep contact fields in sync with seed data (so edits here apply to existing DB)
                existing_vendor.name = vendor_config.get('name', existing_vendor.name)
                existing_vendor.specialization = vendor_config.get('specialization', existing_vendor.specialization)
                existing_vendor.contact_email = vendor_config.get('contact_email', existing_vendor.contact_email)
                existing_vendor.contact_phone = vendor_config.get('contact_phone', existing_vendor.contact_phone)
                existing_vendor.hourly_rate = vendor_config.get('hourly_rate', existing_vendor.hourly_rate)
                if 'emergency_multiplier' in vendor_config:
                    existing_vendor.emergency_multiplier = vendor_config.get('emergency_multiplier')
                existing_vendor.api_endpoint = vendor_config.get('api_endpoint', existing_vendor.api_endpoint)
                existing_vendor.availability_slots = vendor_config.get('availability_slots', existing_vendor.availability_slots)
                db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Error creating vendor {vendor_config['vendor_id']}: {e}")
    
    print(f"✓ Default data created: {len(MACHINE_CONFIG)} machines, {len(users_config)} users, {len(vendors_config)} vendors")