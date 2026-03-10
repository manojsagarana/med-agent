# telemetry_simulator.py
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
import threading
import time

class TelemetrySimulator:
    """Simulates real-time telemetry data for MRI and CT machines"""
    
    MACHINE_IDS = ['mri_brain_01', 'mri_spine_01', 'mri_msk_01', 'ct_chest_01', 'ct_abdo_01']
    
    def __init__(self, data_path=None):
        self.data_path = data_path
        self.historical_data = None
        self.current_readings = {}
        self.machine_profiles = {}
        self.running = False
        self.callbacks = []
        self.start_time = datetime.now()
        self.update_count = {}
        
        # Normal operating ranges (baseline - healthy values)
        self.normal_ranges = {
            'MRI': {
                'Component_Temp': (32, 38),
                'Gradient_Coil_Temp': (38, 48),
                'Vibration_Level': (0.8, 1.5),
                'Cooling_System_Performance': (95, 100),
                'Magnet_Temp_K': (3.95, 4.1),
                'Helium_Level': (92, 100),
                'Helium_Pressure_psi': (15.8, 16.2)
            },
            'CT': {
                'Component_Temp': (32, 40),
                'Gradient_Coil_Temp': (38, 46),
                'Vibration_Level': (0.8, 1.6),
                'Cooling_System_Performance': (94, 100),
                'X_ray_Tube_Temp': (45, 58),
                'Cooling_Oil_Temp': (38, 44)
            }
        }
        
        # Error codes
        self.error_codes = {
            'MRI': {
                0: ['E000'],
                3: ['E101', 'E102', 'E201'],
                5: ['E501', 'E502', 'E601']
            },
            'CT': {
                0: ['E000'],
                3: ['E103', 'E104', 'E202'],
                5: ['E503', 'E504', 'E602']
            }
        }
        
        # Scan types
        self.scan_types = {
            'mri_brain_01': ['Brain Standard', 'Brain Contrast', 'Brain Angio'],
            'mri_spine_01': ['Spine Cervical', 'Spine Thoracic', 'Spine Lumbar'],
            'mri_msk_01': ['Knee', 'Shoulder', 'Hip', 'Ankle'],
            'ct_chest_01': ['Chest Standard', 'Chest HRCT', 'Chest Angio'],
            'ct_abdo_01': ['Abdomen Standard', 'Abdomen Contrast', 'Abdomen Pelvis']
        }
        
        if data_path:
            self._load_historical_data()
        
        self._initialize_machine_profiles()
        self._initialize_all_machines()
    
    def _load_historical_data(self):
        """Load historical data"""
        try:
            self.historical_data = pd.read_csv(self.data_path)
            print(f"Loaded {len(self.historical_data)} historical records")
        except Exception as e:
            print(f"Could not load historical data: {e}")
    
    def _initialize_machine_profiles(self):
        """
        Initialize machine profiles with IMMEDIATE different health states
        This ensures machines don't all start at 100% health
        """
        self.machine_profiles = {
            # MRI Brain 01 - HEALTHY (Normal) - Will slowly degrade
            'mri_brain_01': {
                'status': 'normal',
                'initial_offsets': {
                    'Helium_Level': 0,
                    'Magnet_Temp_K': 0,
                    'Gradient_Coil_Temp': 0,
                    'Cooling_System_Performance': 0,
                    'Vibration_Level': 0
                },
                'degradation': {
                    'active': True,
                    'rate_multiplier': 0.3,
                    'Helium_Level': -0.05,  # Very slow leak
                }
            },
            
            # MRI Spine 01 - MONITOR - Gradient coil running warm
            'mri_spine_01': {
                'status': 'monitor',
                'initial_offsets': {
                    'Gradient_Coil_Temp': 12,      # Already 12°C above normal
                    'Vibration_Level': 0.8,        # Elevated vibration
                    'Cooling_System_Performance': -6,  # Slightly degraded
                    'Helium_Level': -3
                },
                'degradation': {
                    'active': True,
                    'rate_multiplier': 0.4,
                    'Gradient_Coil_Temp': 0.15,
                    'Vibration_Level': 0.02
                }
            },
            
            # MRI MSK 01 - HEALTHY (Normal)
            'mri_msk_01': {
                'status': 'normal',
                'initial_offsets': {
                    'Component_Temp': 2,
                    'Cooling_System_Performance': -2
                },
                'degradation': {
                    'active': False,
                    'rate_multiplier': 0.1
                }
            },
            
            # CT Chest 01 - SCHEDULE MAINTENANCE - X-ray tube degradation
            'ct_chest_01': {
                'status': 'schedule_maintenance',
                'initial_offsets': {
                    'X_ray_Tube_Temp': 18,         # Running hot!
                    'Cooling_Oil_Temp': 10,        # Oil heating up
                    'Vibration_Level': 1.0,
                    'Cooling_System_Performance': -10
                },
                'degradation': {
                    'active': True,
                    'rate_multiplier': 0.5,
                    'X_ray_Tube_Temp': 0.2,
                    'Cooling_Oil_Temp': 0.08
                }
            },
            
            # CT Abdo 01 - MONITOR - Vibration issues starting
            'ct_abdo_01': {
                'status': 'monitor',
                'initial_offsets': {
                    'Vibration_Level': 1.2,
                    'Component_Temp': 5,
                    'Cooling_System_Performance': -5
                },
                'degradation': {
                    'active': True,
                    'rate_multiplier': 0.35,
                    'Vibration_Level': 0.03,
                    'Component_Temp': 0.05
                }
            }
        }
    
    def _initialize_all_machines(self):
        """Initialize readings for all machines with their profiles"""
        for machine_id in self.MACHINE_IDS:
            machine_type = self.get_machine_type(machine_id)
            self.current_readings[machine_id] = self.generate_reading(machine_id, machine_type)
            self.update_count[machine_id] = 0
    
    def get_machine_type(self, machine_id):
        """Get machine type from ID"""
        return 'MRI' if 'mri' in machine_id.lower() else 'CT'
    
    def generate_reading(self, machine_id, machine_type=None, include_degradation=True):
        """Generate telemetry reading with profile-based offsets"""
        if machine_type is None:
            machine_type = self.get_machine_type(machine_id)
        
        profile = self.machine_profiles.get(machine_id, {})
        initial_offsets = profile.get('initial_offsets', {})
        degradation = profile.get('degradation', {})
        
        ranges = self.normal_ranges.get(machine_type, {})
        reading = {
            'machine_id': machine_id,
            'machine_type': machine_type,
            'timestamp': datetime.now().isoformat(),
            'Date': datetime.now().strftime('%Y-%m-%d'),
            'Time': datetime.now().strftime('%H:%M:%S')
        }
        
        # Calculate time-based degradation
        elapsed_minutes = (datetime.now() - self.start_time).total_seconds() / 60
        rate_mult = degradation.get('rate_multiplier', 1.0) if degradation.get('active', False) else 0
        
        # Generate readings with offsets and degradation
        for param, (low, high) in ranges.items():
            # Base value in middle of range
            base_value = (low + high) / 2 + random.uniform(-2, 2)
            
            # Apply initial offset (immediate health state)
            offset = initial_offsets.get(param, 0)
            
            # Apply time-based degradation
            degrade_rate = degradation.get(param, 0)
            time_degradation = degrade_rate * elapsed_minutes * rate_mult if include_degradation else 0
            
            # Calculate final value
            value = base_value + offset + time_degradation
            
            # Add small noise
            noise = random.gauss(0, 0.5)
            value += noise
            
            # Clamp to reasonable bounds
            if param == 'Helium_Level':
                value = max(60, min(100, value))
            elif param == 'Cooling_System_Performance':
                value = max(70, min(100, value))
            elif 'Temp' in param:
                value = max(20, min(95, value))
            elif param == 'Vibration_Level':
                value = max(0.3, min(5.0, value))
            elif param == 'Helium_Pressure_psi':
                value = max(12, min(18, value))
            
            reading[param] = round(value, 2)
        
        # Determine severity
        severity, error_code = self._determine_severity(reading, machine_type)
        reading['Error_Code'] = error_code
        reading['Severity_Level'] = severity
        
        # Add scan type
        reading['Scan_Type'] = random.choice(self.scan_types.get(machine_id, ['General']))
        
        self.current_readings[machine_id] = reading
        self.update_count[machine_id] = self.update_count.get(machine_id, 0) + 1
        
        return reading
    
    def _determine_severity(self, reading, machine_type):
        """Determine severity based on readings - BALANCED THRESHOLDS"""
        critical_score = 0
        warning_score = 0
        
        # Cooling system (lower = worse)
        cooling = reading.get('Cooling_System_Performance', 100)
        if cooling < 80:
            critical_score += 2
        elif cooling < 87:
            warning_score += 2
        elif cooling < 92:
            warning_score += 1
        
        # Vibration (higher = worse)
        vibration = reading.get('Vibration_Level', 1)
        if vibration > 3.5:
            critical_score += 2
        elif vibration > 2.8:
            warning_score += 2
        elif vibration > 2.2:
            warning_score += 1
        
        # Gradient coil temp
        gradient = reading.get('Gradient_Coil_Temp', 45)
        if gradient > 65:
            critical_score += 2
        elif gradient > 56:
            warning_score += 2
        elif gradient > 52:
            warning_score += 1
        
        # Component temp
        comp_temp = reading.get('Component_Temp', 35)
        if comp_temp > 48:
            critical_score += 1
        elif comp_temp > 42:
            warning_score += 1
        
        # MRI specific
        if machine_type == 'MRI':
            helium = reading.get('Helium_Level', 100)
            if helium < 75:
                critical_score += 3
            elif helium < 82:
                warning_score += 2
            elif helium < 88:
                warning_score += 1
            
            magnet = reading.get('Magnet_Temp_K', 4.0)
            if magnet > 4.45:
                critical_score += 2
            elif magnet > 4.25:
                warning_score += 1
        
        # CT specific
        else:
            tube = reading.get('X_ray_Tube_Temp', 50)
            if tube > 82:
                critical_score += 2
            elif tube > 72:
                warning_score += 2
            elif tube > 65:
                warning_score += 1
            
            oil = reading.get('Cooling_Oil_Temp', 40)
            if oil > 55:
                critical_score += 1
            elif oil > 50:
                warning_score += 1
        
        # Determine final severity
        if critical_score >= 3:
            severity = 5
            error_code = random.choice(self.error_codes[machine_type][5])
        elif critical_score >= 1 or warning_score >= 3:
            severity = 3
            error_code = random.choice(self.error_codes[machine_type][3])
        else:
            severity = 0
            error_code = 'E000'
        
        return severity, error_code
    
    def get_current_readings(self, machine_id):
        """Get most recent readings"""
        if machine_id not in self.current_readings:
            machine_type = self.get_machine_type(machine_id)
            self.current_readings[machine_id] = self.generate_reading(machine_id, machine_type)
        return self.current_readings.get(machine_id, {})
    
    def get_all_current_readings(self):
        """Get readings for all machines"""
        return {mid: self.get_current_readings(mid) for mid in self.MACHINE_IDS}
    
    def get_telemetry_history(self, machine_id, hours=24):
        """Get historical telemetry data"""
        history = []
        machine_type = self.get_machine_type(machine_id)
        
        for i in range(min(hours * 4, 50)):
            timestamp = datetime.now() - timedelta(minutes=15 * (hours * 4 - i))
            reading = self.generate_reading(machine_id, machine_type, include_degradation=False)
            reading['timestamp'] = timestamp.isoformat()
            history.append(reading)
        
        return history
    
    def reset_degradation(self, machine_id):
        """Reset machine to healthy state (after maintenance)"""
        if machine_id in self.machine_profiles:
            # Reset all offsets to 0
            self.machine_profiles[machine_id]['initial_offsets'] = {
                k: 0 for k in self.machine_profiles[machine_id].get('initial_offsets', {})
            }
            self.machine_profiles[machine_id]['degradation']['active'] = False
            self.machine_profiles[machine_id]['status'] = 'normal'
            
            # Regenerate reading with healthy values
            machine_type = self.get_machine_type(machine_id)
            self.current_readings[machine_id] = self.generate_reading(machine_id, machine_type)
    
    def set_degradation_active(self, machine_id, active):
        """Enable/disable degradation"""
        if machine_id in self.machine_profiles:
            self.machine_profiles[machine_id]['degradation']['active'] = active
    
    def register_callback(self, callback):
        """Register callback for updates"""
        self.callbacks.append(callback)
    
    def start_simulation(self, interval_seconds=5):
        """Start simulation thread"""
        self.running = True
        
        def simulation_loop():
            while self.running:
                for machine_id in self.MACHINE_IDS:
                    machine_type = self.get_machine_type(machine_id)
                    reading = self.generate_reading(machine_id, machine_type)
                    
                    for callback in self.callbacks:
                        try:
                            callback(machine_id, reading)
                        except Exception as e:
                            print(f"Callback error: {e}")
                
                time.sleep(interval_seconds)
        
        thread = threading.Thread(target=simulation_loop, daemon=True)
        thread.start()
        return thread
    
    def stop_simulation(self):
        """Stop simulation"""
        self.running = False
    
    def inject_fault(self, machine_id, fault_type):
        """Inject fault for testing"""
        if machine_id not in self.machine_profiles:
            return None
        
        faults = {
            'helium_leak': {
                'Helium_Level': -18,
                'Helium_Pressure_psi': -2.5,
                'Magnet_Temp_K': 0.4
            },
            'gradient_overheat': {
                'Gradient_Coil_Temp': 22,
                'Vibration_Level': 1.2,
                'Cooling_System_Performance': -8
            },
            'cooling_failure': {
                'Cooling_System_Performance': -20,
                'Component_Temp': 12,
                'Gradient_Coil_Temp': 10
            },
            'vibration_anomaly': {
                'Vibration_Level': 2.0,
                'Component_Temp': 6
            },
            'tube_overheat': {
                'X_ray_Tube_Temp': 25,
                'Cooling_Oil_Temp': 15,
                'Cooling_System_Performance': -12
            }
        }
        
        if fault_type in faults:
            for param, delta in faults[fault_type].items():
                current = self.machine_profiles[machine_id]['initial_offsets'].get(param, 0)
                self.machine_profiles[machine_id]['initial_offsets'][param] = current + delta
            
            self.machine_profiles[machine_id]['degradation']['active'] = True
            self.machine_profiles[machine_id]['degradation']['rate_multiplier'] = 0.8
        
        # Generate new reading with fault
        machine_type = self.get_machine_type(machine_id)
        reading = self.generate_reading(machine_id, machine_type)
        
        return reading
    
    def get_expected_status(self, machine_id):
        """Get the expected status based on profile"""
        if machine_id in self.machine_profiles:
            return self.machine_profiles[machine_id].get('status', 'normal')
        return 'normal'