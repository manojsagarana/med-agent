# agent.py
import json
from datetime import datetime, timedelta
from enum import Enum
import logging

logging.basicConfig(
    filename='logs/agent.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class RiskTier(Enum):
    NORMAL = 'normal'
    MONITOR = 'monitor'
    SCHEDULE_MAINTENANCE = 'schedule_maintenance'
    CRITICAL = 'critical'


class OperationMode(Enum):
    NORMAL = 'normal'
    LIMP = 'limp'
    STANDBY = 'standby'


class EnergyMode(Enum):
    READY = 'ready'
    ECO = 'eco'
    DEEP_SLEEP = 'deep_sleep'


class MaintenanceAgent:
    """Predictive Equipment Maintenance Agent"""
    
    # All 5 machines
    MACHINE_IDS = ['mri_brain_01', 'mri_spine_01', 'mri_msk_01', 'ct_chest_01', 'ct_abdo_01']
    
    def __init__(self, ml_manager, telemetry_simulator, db, email_service, vendor_api):
        self.ml_manager = ml_manager
        self.telemetry = telemetry_simulator
        self.db = db
        self.email_service = email_service
        self.vendor_api = vendor_api
        
        self.machine_states = {}
        self.alert_history = {}
        self.limp_mode_restrictions = {}
        
        # Initialize all machine states
        for machine_id in self.MACHINE_IDS:
            self._initialize_machine_state(machine_id)
    
    def _initialize_machine_state(self, machine_id):
        """Initialize tracking for a machine"""
        self.machine_states[machine_id] = {
            'status': RiskTier.NORMAL,
            'operation_mode': OperationMode.NORMAL,
            'energy_mode': EnergyMode.READY,
            'last_analysis': None,
            'consecutive_anomalies': 0,
            'last_maintenance': None,
            'pending_alerts': []
        }
    
    def get_machine_type(self, machine_id):
        """Get machine type from ID"""
        return 'MRI' if 'mri' in machine_id.lower() else 'CT'
    
    # ==================== SIMULATED TOOLS ====================
    
    def get_equipment_telemetry(self, machine_id, date_range=None):
        """Tool: Get equipment telemetry data"""
        logging.info(f"TOOL: get_equipment_telemetry called for {machine_id}")
        
        current = self.telemetry.get_current_readings(machine_id)
        history = self.telemetry.get_telemetry_history(machine_id, hours=24)
        
        return {
            'machine_id': machine_id,
            'current_readings': current,
            'history': history,
            'timestamp': datetime.now().isoformat()
        }
    
    def compute_baseline(self, machine_id, lookback_days=30):
        """Tool: Compute operational baseline"""
        logging.info(f"TOOL: compute_baseline called for {machine_id}")
        
        machine_type = self.get_machine_type(machine_id)
        baseline = self.ml_manager.baseline_computer.baselines.get(machine_id)
        
        if not baseline:
            baseline = self.ml_manager.baseline_computer._get_default_baseline()
        
        return {
            'machine_id': machine_id,
            'machine_type': machine_type,
            'lookback_days': lookback_days,
            'baseline': baseline,
            'computed_at': datetime.now().isoformat()
        }
    
    def detect_anomalies(self, machine_id, current_readings, baseline=None):
        """Tool: Detect anomalies in current readings"""
        logging.info(f"TOOL: detect_anomalies called for {machine_id}")
        
        machine_type = self.get_machine_type(machine_id)
        
        anomaly_report = self.ml_manager.anomaly_detector.detect_anomalies(
            current_readings, machine_type
        )
        
        deviation_report = self.ml_manager.baseline_computer.check_deviation(
            current_readings, machine_id
        )
        
        return {
            'machine_id': machine_id,
            'anomaly_detected': anomaly_report['is_anomaly'],
            'anomaly_score': anomaly_report['anomaly_score'],
            'flagged_parameters': anomaly_report['flagged_parameters'],
            'baseline_deviations': deviation_report['deviations'],
            'timestamp': datetime.now().isoformat()
        }
    
    def classify_failure_risk(self, machine_id, anomaly_report):
        """Tool: Classify failure risk"""
        logging.info(f"TOOL: classify_failure_risk called for {machine_id}")
        
        machine_type = self.get_machine_type(machine_id)
        current_readings = self.telemetry.get_current_readings(machine_id)
        
        risk_report = self.ml_manager.failure_predictor.predict_failure_risk(
            current_readings, machine_type, anomaly_report
        )
        
        risk_tier = RiskTier(risk_report['risk_tier'])
        
        return {
            'machine_id': machine_id,
            'risk_tier': risk_tier.value,
            'risk_tier_display': self._get_risk_display(risk_tier),
            'risk_score': risk_report['risk_score'],
            'confidence': risk_report['confidence'],
            'failure_probability': risk_report['failure_probability'],
            'predicted_days_to_failure': risk_report['predicted_days_to_failure'],
            'reasoning': risk_report['reasoning'],
            'feature_importances': risk_report.get('feature_importances', {}),
            'timestamp': datetime.now().isoformat()
        }
    
    def _get_risk_display(self, risk_tier):
        """Get display format for risk tier"""
        displays = {
            RiskTier.NORMAL: {'emoji': '🟢', 'label': 'Normal', 'color': '#28a745'},
            RiskTier.MONITOR: {'emoji': '🟡', 'label': 'Monitor', 'color': '#ffc107'},
            RiskTier.SCHEDULE_MAINTENANCE: {'emoji': '🔴', 'label': 'Schedule Maintenance', 'color': '#dc3545'},
            RiskTier.CRITICAL: {'emoji': '⚫', 'label': 'Critical', 'color': '#212529'}
        }
        return displays.get(risk_tier, displays[RiskTier.NORMAL])
    
    def contact_service_vendor(self, machine_id, fault_summary, urgency, preferred_window):
        """Tool: Contact service vendor"""
        logging.info(f"TOOL: contact_service_vendor called for {machine_id}, urgency: {urgency}")
        
        machine_type = self.get_machine_type(machine_id)
        vendor = self.vendor_api.get_best_vendor(machine_type, urgency)
        
        if not vendor:
            return {'success': False, 'error': 'No available vendors'}
        
        response = self.vendor_api.schedule_service(
            vendor_id=vendor['vendor_id'],
            machine_id=machine_id,
            fault_summary=fault_summary,
            urgency=urgency,
            preferred_window=preferred_window
        )
        
        if response['success'] and self.email_service.enabled:
            self.email_service.send_vendor_notification(
                vendor_email=vendor['email'],
                machine_id=machine_id,
                fault_summary=fault_summary,
                urgency=urgency,
                scheduled_time=response.get('scheduled_time')
            )
        
        return response
    
    def get_scan_schedule(self, machine_id, date_range=None):
        """Tool: Get scan schedule"""
        logging.info(f"TOOL: get_scan_schedule called for {machine_id}")
        
        from database import Appointment, Machine
        
        machine = Machine.query.filter_by(machine_id=machine_id).first()
        if not machine:
            return {'appointments': [], 'error': 'Machine not found'}
        
        if date_range:
            start_date, end_date = date_range
        else:
            start_date = datetime.now()
            end_date = start_date + timedelta(days=7)
        
        appointments = Appointment.query.filter(
            Appointment.machine_id == machine.id,
            Appointment.scheduled_datetime >= start_date,
            Appointment.scheduled_datetime <= end_date,
            Appointment.status.in_(['scheduled', 'in_progress'])
        ).order_by(Appointment.scheduled_datetime).all()
        
        return {
            'machine_id': machine_id,
            'date_range': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'appointments': [
                {
                    'appointment_id': apt.appointment_id,
                    'patient_name': apt.patient_name,
                    'patient_email': apt.patient_email,
                    'scan_type': apt.scan_type,
                    'scheduled_datetime': apt.scheduled_datetime.isoformat(),
                    'duration_minutes': apt.scan_duration_minutes,
                    'priority': apt.priority,
                    'status': apt.status
                }
                for apt in appointments
            ],
            'total_appointments': len(appointments)
        }
    
    def reschedule_appointment(self, appointment_id, new_slot, reason):
        """Tool: Reschedule appointment"""
        logging.info(f"TOOL: reschedule_appointment called for {appointment_id}")
        
        from database import Appointment, db
        
        appointment = Appointment.query.filter_by(appointment_id=appointment_id).first()
        
        if not appointment:
            return {'success': False, 'error': 'Appointment not found'}
        
        old_datetime = appointment.scheduled_datetime
        appointment.original_datetime = old_datetime
        appointment.scheduled_datetime = new_slot
        appointment.status = 'rescheduled'
        appointment.rescheduled_reason = reason
        
        db.session.commit()
        
        if self.email_service.enabled:
            self.email_service.send_patient_reschedule_notification(
                patient_email=appointment.patient_email,
                patient_name=appointment.patient_name,
                old_datetime=old_datetime,
                new_datetime=new_slot,
                reason=reason
            )
        
        return {
            'success': True,
            'appointment_id': appointment_id,
            'old_slot': old_datetime.isoformat(),
            'new_slot': new_slot.isoformat(),
            'notification_sent': self.email_service.enabled
        }
    
    def notify_engineering_team(self, machine_id, risk_report, recommended_action):
        """Tool: Notify engineering team"""
        logging.info(f"TOOL: notify_engineering_team called for {machine_id}")
        
        from database import Alert, Machine, User, db
        from cost_calculator import CostCalculator
        
        machine = Machine.query.filter_by(machine_id=machine_id).first()
        
        cost_calc = CostCalculator()
        cost_analysis = cost_calc.calculate_cost_impact(
            machine_type=machine.machine_type if machine else 'MRI',
            risk_tier=risk_report['risk_tier'],
            failure_type=risk_report.get('reasoning', 'Unknown')
        )
        
        alert = Alert(
            machine_id=machine.id if machine else 1,
            alert_type='failure_prediction',
            severity=risk_report['risk_tier'],
            title=f"{risk_report['risk_tier_display']['emoji']} {risk_report['risk_tier_display']['label']} - {machine_id}",
            description=risk_report['reasoning'],
            affected_parameters=json.dumps(risk_report.get('feature_importances', {})),
            confidence_level=risk_report['confidence'],
            recommended_action=recommended_action,
            estimated_prevention_cost=cost_analysis['prevention_cost'],
            estimated_breakdown_cost=cost_analysis['breakdown_cost']
        )
        
        db.session.add(alert)
        db.session.commit()
        
        engineers = User.query.filter(User.role.in_(['engineer', 'admin'])).all()
        
        if self.email_service.enabled:
            for engineer in engineers:
                self.email_service.send_engineering_alert(
                    recipient_email=engineer.email,
                    recipient_name=engineer.full_name,
                    machine_id=machine_id,
                    risk_report=risk_report,
                    cost_analysis=cost_analysis,
                    recommended_action=recommended_action
                )
        
        return {
            'success': True,
            'alert_id': alert.id,
            'notifications_sent': len(engineers) if self.email_service.enabled else 0,
            'cost_analysis': cost_analysis
        }
    
    # ==================== INTELLIGENT MODES ====================
    
    def determine_limp_mode_restrictions(self, machine_id, risk_report):
        """Intelligent Limp Mode: Determine which scans can still run safely"""
        machine_type = self.get_machine_type(machine_id)
        current_readings = self.telemetry.get_current_readings(machine_id)
        
        restrictions = {
            'mode': 'limp',
            'allowed_scans': [],
            'restricted_scans': [],
            'reason': ''
        }
        
        if machine_type == 'MRI':
            gradient_temp = current_readings.get('Gradient_Coil_Temp', 0)
            helium_level = current_readings.get('Helium_Level', 100)
            
            if gradient_temp > 60:
                restrictions['restricted_scans'] = ['Cardiac MRI', 'Body MRI', 'MSK Complex']
                restrictions['allowed_scans'] = ['Brain Standard', 'Spine Standard']
                restrictions['reason'] = 'Gradient coil overheating - high-power scans restricted'
            elif helium_level < 80:
                restrictions['restricted_scans'] = ['Cardiac MRI', 'Long Duration Scans']
                restrictions['allowed_scans'] = ['Brain Standard', 'Spine Standard', 'Quick Scans']
                restrictions['reason'] = 'Low helium level - extended scans restricted'
            else:
                restrictions['allowed_scans'] = ['Brain Standard', 'Spine Standard']
                restrictions['restricted_scans'] = ['All Complex Scans']
                restrictions['reason'] = 'General degradation detected - limiting to basic scans'
        else:
            tube_temp = current_readings.get('X_ray_Tube_Temp', 50)
            
            if tube_temp > 75:
                restrictions['restricted_scans'] = ['CT Angio', 'Cardiac CT', 'Multi-phase']
                restrictions['allowed_scans'] = ['Head CT', 'Chest Standard', 'Spine CT']
                restrictions['reason'] = 'X-ray tube temperature elevated - high-intensity scans restricted'
            else:
                restrictions['allowed_scans'] = ['Head CT', 'Chest Standard']
                restrictions['restricted_scans'] = ['All Complex Protocols']
                restrictions['reason'] = 'General degradation - limiting scan types'
        
        self.limp_mode_restrictions[machine_id] = restrictions
        return restrictions
    
    def manage_energy_mode(self, machine_id, schedule):
        """Eco-Mode & Smart Energy Optimization"""
        current_time = datetime.now()
        upcoming_appointments = [
            apt for apt in schedule.get('appointments', [])
            if datetime.fromisoformat(apt['scheduled_datetime']) > current_time
        ]
        
        if not upcoming_appointments:
            return {
                'recommended_mode': EnergyMode.DEEP_SLEEP.value,
                'reason': 'No scheduled appointments',
                'wake_time': None
            }
        
        next_appointment = min(
            upcoming_appointments,
            key=lambda x: datetime.fromisoformat(x['scheduled_datetime'])
        )
        next_time = datetime.fromisoformat(next_appointment['scheduled_datetime'])
        time_until_next = (next_time - current_time).total_seconds() / 60
        
        if time_until_next > 120:
            return {
                'recommended_mode': EnergyMode.DEEP_SLEEP.value,
                'reason': f'Next appointment in {int(time_until_next)} minutes',
                'wake_time': (next_time - timedelta(minutes=30)).isoformat()
            }
        elif time_until_next > 30:
            return {
                'recommended_mode': EnergyMode.ECO.value,
                'reason': f'Next appointment in {int(time_until_next)} minutes',
                'wake_time': (next_time - timedelta(minutes=15)).isoformat()
            }
        else:
            return {
                'recommended_mode': EnergyMode.READY.value,
                'reason': 'Appointment imminent',
                'wake_time': None
            }
    
    # ==================== MAIN ANALYSIS ====================
    
    def analyze_machine(self, machine_id):
        """Main analysis function"""
        logging.info(f"Starting analysis for {machine_id}")
        
        # Ensure machine state exists
        if machine_id not in self.machine_states:
            self._initialize_machine_state(machine_id)
        
        # Step 1: Get telemetry
        telemetry_data = self.get_equipment_telemetry(machine_id)
        current_readings = telemetry_data['current_readings']
        
        if not current_readings:
            return {'error': 'No telemetry data available', 'machine_id': machine_id}
        
        # Step 2: Compute/get baseline
        baseline = self.compute_baseline(machine_id)
        
        # Step 3: Detect anomalies
        anomaly_report = self.detect_anomalies(machine_id, current_readings, baseline)
        
        # Step 4: Classify failure risk
        risk_report = self.classify_failure_risk(machine_id, anomaly_report)
        risk_tier = RiskTier(risk_report['risk_tier'])
        
        # Step 5: Get schedule
        schedule = self.get_scan_schedule(machine_id)
        
        # Step 6: Determine operation and energy modes
        energy_recommendation = self.manage_energy_mode(machine_id, schedule)
        
        # Step 7: Take action based on risk tier
        actions_taken = []
        limp_restrictions = None
        
        if risk_tier in [RiskTier.SCHEDULE_MAINTENANCE, RiskTier.CRITICAL]:
            limp_restrictions = self.determine_limp_mode_restrictions(machine_id, risk_report)
            
            preferred_window = self._calculate_preferred_maintenance_window(schedule)
            
            urgency = 'emergency' if risk_tier == RiskTier.CRITICAL else 'scheduled'
            vendor_response = self.contact_service_vendor(
                machine_id=machine_id,
                fault_summary=risk_report['reasoning'],
                urgency=urgency,
                preferred_window=preferred_window
            )
            actions_taken.append({'action': 'vendor_contacted', 'response': vendor_response})
            
            if risk_tier == RiskTier.CRITICAL:
                affected_appointments = self._get_affected_appointments(schedule, preferred_window)
                for apt in affected_appointments[:3]:  # Limit to 3
                    new_slot = self._find_alternative_slot(apt, machine_id)
                    if new_slot:
                        reschedule_result = self.reschedule_appointment(
                            apt['appointment_id'],
                            new_slot,
                            f"Equipment maintenance required: {risk_report['reasoning']}"
                        )
                        actions_taken.append({'action': 'appointment_rescheduled', 'result': reschedule_result})
            
            recommended_action = self._generate_recommended_action(risk_tier, risk_report, limp_restrictions)
            notification_result = self.notify_engineering_team(
                machine_id=machine_id,
                risk_report=risk_report,
                recommended_action=recommended_action
            )
            actions_taken.append({'action': 'team_notified', 'result': notification_result})
            
            self.machine_states[machine_id]['operation_mode'] = OperationMode.LIMP if risk_tier == RiskTier.SCHEDULE_MAINTENANCE else OperationMode.STANDBY
        
        elif risk_tier == RiskTier.MONITOR:
            self.machine_states[machine_id]['consecutive_anomalies'] += 1
            
            if self.machine_states[machine_id]['consecutive_anomalies'] >= 3:
                notification_result = self.notify_engineering_team(
                    machine_id=machine_id,
                    risk_report=risk_report,
                    recommended_action="Persistent anomaly detected. Schedule preventive inspection."
                )
                actions_taken.append({'action': 'team_notified', 'result': notification_result})
        else:
            self.machine_states[machine_id]['consecutive_anomalies'] = 0
            self.machine_states[machine_id]['operation_mode'] = OperationMode.NORMAL
        
        # Update machine state
        self.machine_states[machine_id]['status'] = risk_tier
        self.machine_states[machine_id]['last_analysis'] = datetime.now()
        self.machine_states[machine_id]['energy_mode'] = EnergyMode(energy_recommendation['recommended_mode'])
        
        # Update database
        self._update_machine_database(machine_id, risk_tier, energy_recommendation)
        
        return {
            'machine_id': machine_id,
            'timestamp': datetime.now().isoformat(),
            'telemetry': current_readings,
            'anomaly_report': anomaly_report,
            'risk_report': risk_report,
            'schedule': schedule,
            'energy_mode': energy_recommendation,
            'operation_mode': self.machine_states[machine_id]['operation_mode'].value,
            'limp_restrictions': limp_restrictions,
            'actions_taken': actions_taken
        }
    
    def _calculate_preferred_maintenance_window(self, schedule):
        """Find the best maintenance window"""
        appointments = schedule.get('appointments', [])
        
        if not appointments:
            return {
                'start': datetime.now() + timedelta(hours=2),
                'end': datetime.now() + timedelta(hours=6)
            }
        
        sorted_apts = sorted(appointments, key=lambda x: x['scheduled_datetime'])
        gaps = []
        
        for i in range(len(sorted_apts) - 1):
            end_current = datetime.fromisoformat(sorted_apts[i]['scheduled_datetime']) + timedelta(minutes=sorted_apts[i]['duration_minutes'])
            start_next = datetime.fromisoformat(sorted_apts[i + 1]['scheduled_datetime'])
            gap_duration = (start_next - end_current).total_seconds() / 3600
            
            if gap_duration >= 2:
                gaps.append({
                    'start': end_current,
                    'end': start_next,
                    'duration_hours': gap_duration
                })
        
        if gaps:
            best_gap = max(gaps, key=lambda x: x['duration_hours'])
            return {'start': best_gap['start'], 'end': best_gap['end']}
        
        last_apt = sorted_apts[-1]
        start = datetime.fromisoformat(last_apt['scheduled_datetime']) + timedelta(minutes=last_apt['duration_minutes'] + 30)
        return {'start': start, 'end': start + timedelta(hours=4)}
    
    def _get_affected_appointments(self, schedule, maintenance_window):
        """Get appointments within maintenance window"""
        affected = []
        for apt in schedule.get('appointments', []):
            apt_time = datetime.fromisoformat(apt['scheduled_datetime'])
            if maintenance_window['start'] <= apt_time <= maintenance_window['end']:
                affected.append(apt)
        return affected
    
    def _find_alternative_slot(self, appointment, machine_id):
        """Find alternative slot for rescheduled appointment"""
        original_time = datetime.fromisoformat(appointment['scheduled_datetime'])
        return original_time + timedelta(days=1)
    
    def _generate_recommended_action(self, risk_tier, risk_report, limp_restrictions):
        """Generate recommended action text"""
        if risk_tier == RiskTier.CRITICAL:
            return f"""
CRITICAL ACTION REQUIRED:
1. Immediately suspend machine operations
2. Emergency vendor dispatch has been initiated
3. All affected appointments have been rescheduled
4. Issue: {risk_report['reasoning']}
5. Estimated time to failure: IMMINENT
            """
        elif risk_tier == RiskTier.SCHEDULE_MAINTENANCE:
            allowed = ', '.join(limp_restrictions.get('allowed_scans', [])) if limp_restrictions else 'N/A'
            restricted = ', '.join(limp_restrictions.get('restricted_scans', [])) if limp_restrictions else 'N/A'
            return f"""
MAINTENANCE SCHEDULING REQUIRED:
1. Machine operating in LIMP MODE
2. Allowed scans: {allowed}
3. Restricted scans: {restricted}
4. Issue: {risk_report['reasoning']}
5. Predicted days to failure: {risk_report.get('predicted_days_to_failure', 'N/A')}
6. Vendor has been contacted for scheduled maintenance
            """
        else:
            return f"Continue monitoring. Current status: {risk_report['reasoning']}"
    
    def _update_machine_database(self, machine_id, risk_tier, energy_mode):
        """Update machine status in database"""
        from database import Machine, db
        
        machine = Machine.query.filter_by(machine_id=machine_id).first()
        if machine:
            machine.status = risk_tier.value
            machine.operation_mode = self.machine_states[machine_id]['operation_mode'].value
            machine.energy_mode = energy_mode['recommended_mode']
            db.session.commit()
    
    def get_dashboard_data(self):
        """Get comprehensive data for dashboard display"""
        dashboard_data = {
            'machines': [],
            'alerts': [],
            'kpis': {},
            'energy_savings': {},
            'timestamp': datetime.now().isoformat()
        }
        
        for machine_id in self.MACHINE_IDS:
            if machine_id not in self.machine_states:
                self._initialize_machine_state(machine_id)
            
            state = self.machine_states[machine_id]
            readings = self.telemetry.get_current_readings(machine_id)
            
            machine_data = {
                'machine_id': machine_id,
                'machine_type': self.get_machine_type(machine_id),
                'status': state['status'].value,
                'status_display': self._get_risk_display(state['status']),
                'operation_mode': state['operation_mode'].value,
                'energy_mode': state['energy_mode'].value,
                'current_readings': readings,
                'limp_restrictions': self.limp_mode_restrictions.get(machine_id),
                'last_analysis': state['last_analysis'].isoformat() if state['last_analysis'] else None
            }
            dashboard_data['machines'].append(machine_data)
        
        return dashboard_data