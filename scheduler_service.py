from datetime import datetime, timedelta
import random
import string

class SchedulerService:
    """Manages patient appointments and machine scheduling"""
    
    def __init__(self, db):
        self.db = db
    
    def generate_sample_appointments(self, machine_id, days=7, appointments_per_day=5):
        """Generate sample appointments for testing"""
        from database import Appointment, Machine
        
        machine = Machine.query.filter_by(machine_id=machine_id).first()
        if not machine:
            return []
        
        machine_type = 'MRI' if 'MRI' in machine_id else 'CT'
        
        scan_types = {
            'MRI': ['Brain MRI', 'Spine MRI', 'Cardiac MRI', 'Abdominal MRI', 'MSK MRI', 'Breast MRI'],
            'CT': ['Head CT', 'Chest CT', 'Abdominal CT', 'Spine CT', 'Cardiac CT', 'CT Angiography']
        }
        
        patient_names = [
            'John Smith', 'Emily Johnson', 'Michael Williams', 'Sarah Brown',
            'David Jones', 'Jennifer Garcia', 'Robert Miller', 'Lisa Davis',
            'William Rodriguez', 'Elizabeth Martinez', 'James Anderson', 'Patricia Taylor'
        ]
        
        appointments = []
        current_date = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
        
        for day in range(days):
            date = current_date + timedelta(days=day)
            
            # Skip weekends
            if date.weekday() >= 5:
                continue
            
            for apt_num in range(appointments_per_day):
                # Schedule between 8 AM and 5 PM
                hour = 8 + (apt_num * 2)  # 2-hour intervals
                if hour >= 17:
                    continue
                
                scheduled_time = date.replace(hour=hour, minute=random.choice([0, 30]))
                
                # Generate appointment ID
                apt_id = f"APT-{machine_id}-{scheduled_time.strftime('%Y%m%d%H%M')}-{random.randint(100, 999)}"
                
                appointment = Appointment(
                    appointment_id=apt_id,
                    machine_id=machine.id,
                    patient_name=random.choice(patient_names),
                    patient_email=random.choice([
                        'azim.niyaz@gmail.com',
                        'azim.niyaz@gmail.com', 
                        'azim.niyaz@gmail.com'
                    ]),
                    patient_phone=f"+1-555-{random.randint(1000, 9999)}",
                    patient_id=f"PAT-{random.randint(10000, 99999)}",
                    scan_type=random.choice(scan_types[machine_type]),
                    scan_duration_minutes=random.choice([30, 45, 60, 90]),
                    priority=random.choices(['normal', 'urgent', 'emergency'], weights=[0.8, 0.15, 0.05])[0],
                    scheduled_datetime=scheduled_time,
                    status='scheduled'
                )
                
                self.db.session.add(appointment)
                appointments.append(appointment)
        
        self.db.session.commit()
        return appointments
    
    def find_available_slots(self, machine_id, date, duration_minutes=60):
        """Find available time slots for a given date"""
        from database import Appointment, Machine
        
        machine = Machine.query.filter_by(machine_id=machine_id).first()
        if not machine:
            return []
        
        # Get existing appointments for the date
        start_of_day = datetime.combine(date, datetime.min.time()).replace(hour=8)
        end_of_day = datetime.combine(date, datetime.min.time()).replace(hour=17)
        
        existing_appointments = Appointment.query.filter(
            Appointment.machine_id == machine.id,
            Appointment.scheduled_datetime >= start_of_day,
            Appointment.scheduled_datetime < end_of_day,
            Appointment.status.in_(['scheduled', 'in_progress'])
        ).order_by(Appointment.scheduled_datetime).all()
        
        # Find gaps
        available_slots = []
        current_time = start_of_day
        
        for apt in existing_appointments:
            # Check if there's a gap before this appointment
            if (apt.scheduled_datetime - current_time).total_seconds() / 60 >= duration_minutes:
                available_slots.append({
                    'start': current_time,
                    'end': apt.scheduled_datetime,
                    'duration_available': (apt.scheduled_datetime - current_time).total_seconds() / 60
                })
            
            current_time = apt.scheduled_datetime + timedelta(minutes=apt.scan_duration_minutes)
        
        # Check for slot at the end of the day
        if (end_of_day - current_time).total_seconds() / 60 >= duration_minutes:
            available_slots.append({
                'start': current_time,
                'end': end_of_day,
                'duration_available': (end_of_day - current_time).total_seconds() / 60
            })
        
        return available_slots
    
    def get_daily_schedule(self, machine_id, date):
        """Get complete schedule for a specific day"""
        from database import Appointment, Machine, MaintenanceRecord
        
        machine = Machine.query.filter_by(machine_id=machine_id).first()
        if not machine:
            return {'error': 'Machine not found'}
        
        start_of_day = datetime.combine(date, datetime.min.time())
        end_of_day = start_of_day + timedelta(days=1)
        
        appointments = Appointment.query.filter(
            Appointment.machine_id == machine.id,
            Appointment.scheduled_datetime >= start_of_day,
            Appointment.scheduled_datetime < end_of_day
        ).order_by(Appointment.scheduled_datetime).all()
        
        maintenance = MaintenanceRecord.query.filter(
            MaintenanceRecord.machine_id == machine.id,
            MaintenanceRecord.scheduled_date >= start_of_day,
            MaintenanceRecord.scheduled_date < end_of_day
        ).all()
        
        schedule = {
            'date': date.isoformat(),
            'machine_id': machine_id,
            'appointments': [
                {
                    'id': apt.appointment_id,
                    'time': apt.scheduled_datetime.strftime('%H:%M'),
                    'patient': apt.patient_name,
                    'scan_type': apt.scan_type,
                    'duration': apt.scan_duration_minutes,
                    'priority': apt.priority,
                    'status': apt.status
                }
                for apt in appointments
            ],
            'maintenance': [
                {
                    'id': m.id,
                    'time': m.scheduled_date.strftime('%H:%M') if m.scheduled_date else 'TBD',
                    'type': m.maintenance_type,
                    'status': m.status
                }
                for m in maintenance
            ],
            'total_appointments': len(appointments),
            'total_scan_time': sum(apt.scan_duration_minutes for apt in appointments)
        }
        
        return schedule
    
    def reschedule_appointments_for_maintenance(self, machine_id, maintenance_start, maintenance_end):
        """Reschedule all appointments that conflict with maintenance window"""
        from database import Appointment, Machine
        
        machine = Machine.query.filter_by(machine_id=machine_id).first()
        if not machine:
            return {'error': 'Machine not found'}
        
        # Find conflicting appointments
        conflicting = Appointment.query.filter(
            Appointment.machine_id == machine.id,
            Appointment.scheduled_datetime >= maintenance_start,
            Appointment.scheduled_datetime < maintenance_end,
            Appointment.status == 'scheduled'
        ).all()
        
        rescheduled = []
        
        for apt in conflicting:
            # Find next available slot
            new_date = maintenance_end.date()
            for day_offset in range(7):  # Look up to 7 days ahead
                check_date = new_date + timedelta(days=day_offset)
                if check_date.weekday() < 5:  # Skip weekends
                    slots = self.find_available_slots(machine_id, check_date, apt.scan_duration_minutes)
                    if slots:
                        new_slot = slots[0]['start']
                        apt.original_datetime = apt.scheduled_datetime
                        apt.scheduled_datetime = new_slot
                        apt.status = 'rescheduled'
                        apt.rescheduled_reason = 'Equipment maintenance'
                        rescheduled.append({
                            'appointment_id': apt.appointment_id,
                            'patient': apt.patient_name,
                            'old_time': apt.original_datetime.isoformat(),
                            'new_time': new_slot.isoformat()
                        })
                        break
        
        self.db.session.commit()
        
        return {
            'total_conflicting': len(conflicting),
            'total_rescheduled': len(rescheduled),
            'rescheduled_appointments': rescheduled
        }