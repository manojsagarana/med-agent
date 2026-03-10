import requests
import json
from datetime import datetime, timedelta
import logging
import random
import string

class VendorAPI:
    """Simulated Vendor API for service coordination"""
    
    def __init__(self):
        self.vendors = {
            'VENDOR-001': {
                'vendor_id': 'VENDOR-001',
                'name': 'MedTech Service Solutions',
                'specialization': 'Both',
                'email': 'service@medtechsolutions.com',
                'phone': '+1-555-0101',
                'api_endpoint': 'https://api.medtechsolutions.com/service',
                'hourly_rate': 250.00,
                'emergency_multiplier': 1.5,
                'availability': self._generate_availability(),
                'response_time_hours': {'scheduled': 48, 'emergency': 4}
            },
            'VENDOR-002': {
                'vendor_id': 'VENDOR-002',
                'name': 'Imaging Equipment Experts',
                'specialization': 'MRI',
                'email': 'support@imagingexperts.com',
                'phone': '+1-555-0102',
                'api_endpoint': 'https://api.imagingexperts.com/service',
                'hourly_rate': 280.00,
                'emergency_multiplier': 2.0,
                'availability': self._generate_availability(),
                'response_time_hours': {'scheduled': 24, 'emergency': 2}
            }
        }
        
        self.service_requests = {}
        self.service_history = []
    
    def _generate_availability(self):
        """Generate availability slots for next 14 days"""
        availability = {}
        current_date = datetime.now().date()
        
        for i in range(14):
            date = current_date + timedelta(days=i)
            day_name = date.strftime('%A').lower()
            
            if day_name in ['saturday', 'sunday']:
                slots = ['10:00-14:00'] if random.random() > 0.5 else []
            else:
                slots = ['09:00-12:00', '13:00-17:00']
            
            availability[date.isoformat()] = slots
        
        return availability
    
    def get_best_vendor(self, machine_type, urgency):
        """Find the best available vendor for the request"""
        matching_vendors = []
        
        for vendor_id, vendor in self.vendors.items():
            if vendor['specialization'] in [machine_type, 'Both']:
                # Calculate score based on response time and rate
                response_time = vendor['response_time_hours'].get(urgency, 48)
                rate = vendor['hourly_rate']
                if urgency == 'emergency':
                    rate *= vendor['emergency_multiplier']
                
                score = 1 / (response_time + rate / 100)  # Higher is better
                
                matching_vendors.append({
                    **vendor,
                    'score': score,
                    'effective_rate': rate
                })
        
        if not matching_vendors:
            return None
        
        # Sort by score and return best
        matching_vendors.sort(key=lambda x: x['score'], reverse=True)
        return matching_vendors[0]
    
    def schedule_service(self, vendor_id, machine_id, fault_summary, urgency, preferred_window):
        """
        Schedule service with vendor (simulated API call)
        In production, this would make actual HTTP requests to vendor APIs
        """
        logging.info(f"API CALL: Scheduling service with {vendor_id} for {machine_id}")
        
        vendor = self.vendors.get(vendor_id)
        if not vendor:
            return {'success': False, 'error': 'Vendor not found'}
        
        # Simulate API request
        request_payload = {
            'request_id': self._generate_request_id(),
            'vendor_id': vendor_id,
            'machine_id': machine_id,
            'fault_summary': fault_summary,
            'urgency': urgency,
            'preferred_window': {
                'start': preferred_window['start'].isoformat() if isinstance(preferred_window['start'], datetime) else preferred_window['start'],
                'end': preferred_window['end'].isoformat() if isinstance(preferred_window['end'], datetime) else preferred_window['end']
            },
            'hospital_id': 'HOSP-001',
            'contact_email': 'engineering@hospital.com',
            'contact_phone': '+1-555-HOSPITAL',
            'timestamp': datetime.now().isoformat()
        }
        
        # Simulate API response
        response = self._simulate_vendor_api_response(request_payload, vendor)
        
        # Store request
        self.service_requests[request_payload['request_id']] = {
            'request': request_payload,
            'response': response,
            'status': 'pending' if response['success'] else 'failed'
        }
        
        self.service_history.append({
            'timestamp': datetime.now().isoformat(),
            'vendor_id': vendor_id,
            'machine_id': machine_id,
            'request_id': request_payload['request_id'],
            'urgency': urgency,
            'success': response['success']
        })
        
        return response
    
    def _generate_request_id(self):
        """Generate unique request ID"""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        return f"SR-{timestamp}-{random_suffix}"
    
    def _simulate_vendor_api_response(self, request, vendor):
        """Simulate vendor API response"""
        # Simulate occasional failures (5% chance)
        if random.random() < 0.05:
            return {
                'success': False,
                'error': 'Vendor service temporarily unavailable',
                'retry_after': 300
            }
        
        # Calculate scheduled time based on urgency
        if request['urgency'] == 'emergency':
            response_hours = vendor['response_time_hours']['emergency']
            scheduled_time = datetime.now() + timedelta(hours=response_hours)
        else:
            # Try to match preferred window
            preferred_start = datetime.fromisoformat(request['preferred_window']['start']) if isinstance(request['preferred_window']['start'], str) else request['preferred_window']['start']
            scheduled_time = preferred_start
        
        # Estimate cost
        estimated_hours = random.uniform(2, 6)
        hourly_rate = vendor['hourly_rate']
        if request['urgency'] == 'emergency':
            hourly_rate *= vendor['emergency_multiplier']
        
        estimated_cost = estimated_hours * hourly_rate
        
        return {
            'success': True,
            'request_id': request['request_id'],
            'vendor_confirmation_id': f"VND-{random.randint(10000, 99999)}",
            'vendor_name': vendor['name'],
            'scheduled_time': scheduled_time.isoformat(),
            'estimated_duration_hours': round(estimated_hours, 1),
            'estimated_cost': round(estimated_cost, 2),
            'technician_name': random.choice(['John Smith', 'Sarah Johnson', 'Mike Wilson', 'Emily Brown']),
            'technician_phone': f"+1-555-{random.randint(1000, 9999)}",
            'message': f"Service request confirmed. Technician will arrive at {scheduled_time.strftime('%Y-%m-%d %H:%M')}."
        }
    
    def get_service_status(self, request_id):
        """Get status of a service request"""
        request_data = self.service_requests.get(request_id)
        if not request_data:
            return {'error': 'Request not found'}
        
        return {
            'request_id': request_id,
            'status': request_data['status'],
            'vendor_response': request_data['response'],
            'last_updated': datetime.now().isoformat()
        }
    
    def update_service_status(self, request_id, new_status, notes=None):
        """Update service request status (simulates vendor callback)"""
        if request_id in self.service_requests:
            self.service_requests[request_id]['status'] = new_status
            if notes:
                self.service_requests[request_id]['notes'] = notes
            return True
        return False
    
    def get_vendor_availability(self, vendor_id, date):
        """Get vendor availability for a specific date"""
        vendor = self.vendors.get(vendor_id)
        if not vendor:
            return []
        
        date_str = date.isoformat() if isinstance(date, datetime) else date
        return vendor['availability'].get(date_str, [])