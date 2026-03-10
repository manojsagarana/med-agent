# maintenance_scheduler.py
from datetime import datetime, timedelta
from database import db, Machine, Alert, MaintenanceRecord, Vendor, Appointment, User, EmailLog
import json
import logging

class MaintenanceScheduler:
    """Handles automated vendor scheduling and patient notifications"""
    
    def __init__(self, email_service, vendor_api):
        self.email_service = email_service
        self.vendor_api = vendor_api
    
    def schedule_maintenance_for_alert(self, alert, machine, predicted_days_to_failure=None):
        """
        Schedule vendor maintenance based on alert severity
        - Critical: Immediate (within 4 hours)
        - Schedule Maintenance: Last day before predicted failure
        """
        if machine.maintenance_scheduled:
            logging.info(f"Maintenance already scheduled for {machine.machine_id}")
            return None
        
        severity = alert.severity
        
        if severity == 'critical':
            # Immediate scheduling
            scheduled_date = datetime.now() + timedelta(hours=4)
            maintenance_type = 'emergency'
            urgency = 'emergency'
        elif severity == 'schedule_maintenance':
            # Schedule for day before predicted failure
            if predicted_days_to_failure and predicted_days_to_failure > 1:
                scheduled_date = datetime.now() + timedelta(days=predicted_days_to_failure - 1)
            else:
                scheduled_date = datetime.now() + timedelta(days=7)  # Default 7 days
            maintenance_type = 'scheduled'
            urgency = 'scheduled'
        else:
            return None  # Don't schedule for monitor/normal
        
        # Find best vendor
        vendor = self._get_best_vendor(machine.machine_type, urgency)
        if not vendor:
            logging.error(f"No vendor available for {machine.machine_id}")
            return None
        
        # Create maintenance record
        maintenance_record = MaintenanceRecord(
            machine_id=machine.id,
            vendor_id=vendor.id,
            alert_id=alert.id,
            maintenance_type=maintenance_type,
            status='scheduled',
            scheduled_date=scheduled_date,
            fault_summary=alert.description,
            estimated_cost=self._estimate_cost(vendor, maintenance_type)
        )
        
        db.session.add(maintenance_record)
        
        # Update machine
        machine.maintenance_scheduled = True
        machine.scheduled_maintenance_date = scheduled_date
        
        # Update alert
        alert.vendor_contacted = True
        alert.vendor_scheduled_date = scheduled_date
        
        db.session.commit()
        
        # Send notifications to all stakeholders
        self._send_all_notifications(machine, alert, maintenance_record, vendor, scheduled_date)
        
        # Reschedule affected patients
        self._reschedule_affected_appointments(machine, scheduled_date, maintenance_record)
        
        return maintenance_record
    
    def _get_best_vendor(self, machine_type, urgency):
        """Get the best available vendor"""
        if machine_type == 'MRI':
            vendor = Vendor.query.filter(
                Vendor.specialization.in_(['MRI', 'Both']),
                Vendor.is_active == True
            ).first()
        else:
            vendor = Vendor.query.filter(
                Vendor.specialization.in_(['CT', 'Both']),
                Vendor.is_active == True
            ).first()
        
        return vendor
    
    def _estimate_cost(self, vendor, maintenance_type):
        """Estimate maintenance cost"""
        base_hours = 4 if maintenance_type == 'emergency' else 6
        rate = vendor.hourly_rate or 250
        
        if maintenance_type == 'emergency':
            rate *= vendor.emergency_multiplier or 1.5
        
        return round(base_hours * rate, 2)
    
    def _send_all_notifications(self, machine, alert, maintenance_record, vendor, scheduled_date):
        """Send notifications to all stakeholders (only once)"""
        
        # Check if we already sent notifications for this alert
        if not EmailLog.can_send_email(machine.machine_id, 'maintenance', alert.severity, cooldown_minutes=60):
            logging.info(f"Skipping notifications - already sent recently for {machine.machine_id}")
            return
        
        # Get all users to notify
        users = User.query.filter(User.role.in_(['admin', 'engineer', 'radiologist'])).all()
        recipients = [u.email for u in users]
        
        # Log the email
        email_log = EmailLog(
            machine_id=machine.machine_id,
            email_type='maintenance',
            severity=alert.severity,
            recipients=json.dumps(recipients),
            subject=f"Maintenance Scheduled - {machine.machine_id}"
        )
        db.session.add(email_log)
        db.session.commit()
        
        # Send emails if enabled
        if self.email_service and self.email_service.enabled:
            # Send to staff
            for user in users:
                self.email_service.send_maintenance_scheduled_notification(
                    recipient_email=user.email,
                    recipient_name=user.full_name,
                    machine=machine,
                    alert=alert,
                    scheduled_date=scheduled_date,
                    vendor=vendor
                )
            
            # Send to vendor
            self.email_service.send_vendor_maintenance_request(
                vendor=vendor,
                machine=machine,
                alert=alert,
                scheduled_date=scheduled_date,
                maintenance_type=maintenance_record.maintenance_type
            )
        
        maintenance_record.notifications_sent = True
        db.session.commit()
        
        logging.info(f"Notifications sent for {machine.machine_id} maintenance")
    
    def _reschedule_affected_appointments(self, machine, maintenance_date, maintenance_record):
        """Reschedule appointments that conflict with maintenance"""
        # Maintenance window: 4 hours for scheduled, 8 hours for emergency
        if maintenance_record.maintenance_type == 'emergency':
            maintenance_end = maintenance_date + timedelta(hours=8)
        else:
            maintenance_end = maintenance_date + timedelta(hours=4)
        
        # Find conflicting appointments
        affected_appointments = Appointment.query.filter(
            Appointment.machine_id == machine.id,
            Appointment.scheduled_datetime >= maintenance_date,
            Appointment.scheduled_datetime <= maintenance_end,
            Appointment.status == 'scheduled'
        ).all()
        
        rescheduled_count = 0
        
        for apt in affected_appointments:
            # Find new slot (next day, same time)
            new_datetime = apt.scheduled_datetime + timedelta(days=1)
            
            # Store original time
            apt.original_datetime = apt.scheduled_datetime
            apt.scheduled_datetime = new_datetime
            apt.status = 'rescheduled'
            apt.rescheduled_reason = f"Equipment maintenance scheduled: {maintenance_record.fault_summary[:100] if maintenance_record.fault_summary else 'Preventive maintenance'}"
            
            # Send patient notification
            if self.email_service and self.email_service.enabled and apt.patient_email:
                self.email_service.send_patient_reschedule_notification(
                    patient_email=apt.patient_email,
                    patient_name=apt.patient_name,
                    old_datetime=apt.original_datetime,
                    new_datetime=new_datetime,
                    reason=apt.rescheduled_reason,
                    machine_id=machine.machine_id
                )
                apt.notification_sent = True
                apt.notification_sent_at = datetime.utcnow()
            
            rescheduled_count += 1
        
        maintenance_record.patients_rescheduled = rescheduled_count
        db.session.commit()
        
        logging.info(f"Rescheduled {rescheduled_count} appointments for {machine.machine_id}")
        
        return rescheduled_count