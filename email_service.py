# email_service.py
from flask_mail import Mail, Message
from datetime import datetime
import logging

mail = Mail()

class EmailService:
    """Email notification service"""
    
    def __init__(self, app=None):
        self.app = app
        self.enabled = False
    
    def init_app(self, app):
        self.app = app
        mail.init_app(app)
    
    def send_maintenance_scheduled_notification(self, recipient_email, recipient_name, machine, alert, scheduled_date, vendor):
        """Send maintenance scheduling notification to staff"""
        if not self.enabled or not self.app:
            logging.info(f"Email disabled. Would notify {recipient_email} about maintenance for {machine.machine_id}")
            return True
        
        try:
            subject = f"🔧 Maintenance Scheduled - {machine.machine_id}"
            
            body = f"""
MAINTENANCE SCHEDULING NOTIFICATION
====================================

Dear {recipient_name},

Maintenance has been automatically scheduled for the following equipment:

MACHINE DETAILS:
- Machine ID: {machine.machine_id}
- Type: {machine.machine_type}
- Location: {machine.location}

ALERT DETAILS:
- Severity: {alert.severity.upper()}
- Issue: {alert.description}
- Confidence: {alert.confidence_level:.1f}%

MAINTENANCE SCHEDULE:
- Scheduled Date: {scheduled_date.strftime('%A, %B %d, %Y at %I:%M %p')}
- Vendor: {vendor.name}
- Vendor Contact: {vendor.contact_email} / {vendor.contact_phone}
- Estimated Cost: ${alert.estimated_prevention_cost:,.2f}

COST IMPACT:
- Prevention Cost: ${alert.estimated_prevention_cost:,.2f}
- Potential Breakdown Cost: ${alert.estimated_breakdown_cost:,.2f}
- Savings: ${(alert.estimated_breakdown_cost - alert.estimated_prevention_cost):,.2f}

ACTION REQUIRED:
- Affected patient appointments have been automatically rescheduled
- Please review and confirm the maintenance schedule
- Log into the dashboard for full details: http://localhost:5000/dashboard

---
This is an automated message from the Predictive Maintenance System.
            """
            
            msg = Message(
                subject=subject,
                recipients=[recipient_email],
                body=body
            )
            
            with self.app.app_context():
                mail.send(msg)
            
            logging.info(f"Maintenance notification sent to {recipient_email}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to send email: {e}")
            return False
    
    def send_vendor_maintenance_request(self, vendor, machine, alert, scheduled_date, maintenance_type):
        """Send maintenance request to vendor"""
        if not self.enabled or not self.app:
            logging.info(f"Email disabled. Would send maintenance request to vendor {vendor.contact_email}")
            return True
        
        try:
            urgency = "🚨 EMERGENCY" if maintenance_type == 'emergency' else "📅 SCHEDULED"
            subject = f"{urgency} Maintenance Request - {machine.machine_id}"
            
            body = f"""
MAINTENANCE SERVICE REQUEST
============================

{urgency} SERVICE REQUIRED

HOSPITAL: City Medical Center
CONTACT: Engineering Department
PHONE: +1-555-HOSPITAL
EMAIL: engineering@hospital.com

EQUIPMENT DETAILS:
- Machine ID: {machine.machine_id}
- Type: {machine.machine_type}
- Model: {machine.model}
- Manufacturer: {machine.manufacturer}
- Location: {machine.location}

FAULT DETAILS:
- Issue: {alert.description}
- Severity: {alert.severity.upper()}
- Error Code: {alert.title}

SCHEDULING:
- Requested Date: {scheduled_date.strftime('%A, %B %d, %Y')}
- Requested Time: {scheduled_date.strftime('%I:%M %p')}
- Estimated Duration: {'4-8 hours' if maintenance_type == 'emergency' else '2-4 hours'}

Please confirm receipt and your availability.

---
This is an automated request from the Hospital Predictive Maintenance System.
            """
            
            msg = Message(
                subject=subject,
                recipients=[vendor.contact_email],
                body=body
            )
            
            with self.app.app_context():
                mail.send(msg)
            
            logging.info(f"Vendor request sent to {vendor.contact_email}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to send vendor email: {e}")
            return False
    
    def send_patient_reschedule_notification(self, patient_email, patient_name, old_datetime, new_datetime, reason, machine_id=None):
        """Send appointment reschedule notification to patient"""
        if not self.enabled or not self.app:
            logging.info(f"Email disabled. Would notify patient {patient_email} about rescheduling")
            return True
        
        try:
            subject = "📅 Appointment Rescheduled - Hospital Radiology"
            
            old_time_str = old_datetime.strftime('%A, %B %d, %Y at %I:%M %p') if hasattr(old_datetime, 'strftime') else str(old_datetime)
            new_time_str = new_datetime.strftime('%A, %B %d, %Y at %I:%M %p') if hasattr(new_datetime, 'strftime') else str(new_datetime)
            
            body = f"""
Dear {patient_name},

We regret to inform you that your scheduled appointment has been rescheduled due to essential equipment maintenance.

ORIGINAL APPOINTMENT:
- Date/Time: {old_time_str}
- Status: RESCHEDULED

NEW APPOINTMENT:
- Date/Time: {new_time_str}
- Status: CONFIRMED

REASON FOR CHANGE:
{reason}

IMPORTANT:
- Please arrive 15 minutes before your new appointment time
- Bring your ID and insurance information
- If this time doesn't work, please contact us to reschedule

CONTACT US:
- Phone: +1-555-SCHEDULE
- Email: scheduling@hospital.com
- Online: http://localhost:5000/schedules

We apologize for any inconvenience and thank you for your understanding.

Best regards,
Hospital Radiology Department

---
This is an automated message. Please do not reply directly to this email.
            """
            
            msg = Message(
                subject=subject,
                recipients=[patient_email],
                body=body
            )
            
            with self.app.app_context():
                mail.send(msg)
            
            logging.info(f"Reschedule notification sent to {patient_email}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to send patient email: {e}")
            return False
    
    def send_alert_notification(self, recipient_email, recipient_name, machine_id, alert, cost_analysis):
        """Send alert notification (one-time)"""
        if not self.enabled or not self.app:
            logging.info(f"Email disabled. Would send alert to {recipient_email}")
            return True
        
        try:
            emoji = '⚫' if alert.severity == 'critical' else '🔴' if alert.severity == 'schedule_maintenance' else '🟡'
            subject = f"{emoji} Equipment Alert - {machine_id}"
            
            body = f"""
EQUIPMENT ALERT NOTIFICATION
=============================

Dear {recipient_name},

An alert has been generated for equipment requiring attention:

MACHINE: {machine_id}
SEVERITY: {alert.severity.upper()}
TIME: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}

ISSUE:
{alert.description}

RECOMMENDED ACTION:
{alert.recommended_action}

COST ANALYSIS:
- Prevention Cost: ${cost_analysis.get('prevention_cost', 0):,.2f}
- Breakdown Cost: ${cost_analysis.get('breakdown_cost', 0):,.2f}
- Potential Savings: ${cost_analysis.get('potential_savings', 0):,.2f}

{f"⚠️ MAINTENANCE HAS BEEN AUTOMATICALLY SCHEDULED" if alert.vendor_contacted else "Please review and take appropriate action."}

Dashboard: http://localhost:5000/dashboard

---
This is an automated alert from the Predictive Maintenance System.
            """
            
            msg = Message(
                subject=subject,
                recipients=[recipient_email],
                body=body
            )
            
            with self.app.app_context():
                mail.send(msg)
            
            return True
            
        except Exception as e:
            logging.error(f"Failed to send alert email: {e}")
            return False