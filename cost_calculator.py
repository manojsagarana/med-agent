from datetime import datetime
import json

class CostCalculator:
    """
    Calculates cost impact of maintenance decisions
    Compares preventive maintenance vs breakdown costs
    """
    
    def __init__(self):
        # Base costs for different maintenance scenarios
        self.cost_data = {
            'MRI': {
                'preventive': {
                    'helium_refill': 5000,
                    'gradient_coil_service': 8000,
                    'cooling_system_service': 3500,
                    'general_inspection': 2000,
                    'calibration': 1500
                },
                'corrective': {
                    'helium_refill': 7500,
                    'gradient_coil_repair': 25000,
                    'cooling_system_repair': 12000,
                    'general_repair': 8000,
                    'magnet_service': 50000
                },
                'emergency': {
                    'helium_emergency': 15000,
                    'gradient_coil_replacement': 75000,
                    'cooling_system_replacement': 35000,
                    'emergency_callout': 5000,
                    'magnet_quench_recovery': 150000
                },
                'downtime_cost_per_hour': 1500,  # Lost revenue per hour
                'average_scans_per_day': 12,
                'revenue_per_scan': 1200
            },
            'CT': {
                'preventive': {
                    'tube_service': 4000,
                    'cooling_service': 2500,
                    'detector_calibration': 3000,
                    'general_inspection': 1500,
                    'software_update': 500
                },
                'corrective': {
                    'tube_repair': 15000,
                    'cooling_repair': 8000,
                    'detector_repair': 20000,
                    'general_repair': 6000
                },
                'emergency': {
                    'tube_replacement': 80000,
                    'cooling_replacement': 25000,
                    'detector_replacement': 60000,
                    'emergency_callout': 4000
                },
                'downtime_cost_per_hour': 1200,
                'average_scans_per_day': 20,
                'revenue_per_scan': 800
            }
        }
        
        # Labor costs
        self.labor_costs = {
            'regular_hourly': 150,
            'overtime_hourly': 225,
            'emergency_hourly': 300,
            'average_repair_hours': {
                'preventive': 3,
                'corrective': 8,
                'emergency': 12
            }
        }
        
        # Additional costs
        self.additional_costs = {
            'patient_rescheduling_per_patient': 50,
            'administrative_overhead': 0.15,  # 15% of total
            'parts_markup': 0.20  # 20% markup on parts
        }
    
    def calculate_cost_impact(self, machine_type, risk_tier, failure_type):
        """
        Calculate full cost impact analysis
        """
        costs = self.cost_data.get(machine_type, self.cost_data['MRI'])
        
        # Determine failure category from failure type
        failure_category = self._categorize_failure(failure_type, machine_type)
        
        # Calculate preventive maintenance cost
        prevention_cost = self._calculate_prevention_cost(costs, failure_category)
        
        # Calculate potential breakdown cost
        breakdown_cost = self._calculate_breakdown_cost(costs, failure_category, risk_tier)
        
        # Calculate ROI of preventive action
        roi = ((breakdown_cost - prevention_cost) / prevention_cost * 100) if prevention_cost > 0 else 0
        
        return {
            'prevention_cost': round(prevention_cost, 2),
            'breakdown_cost': round(breakdown_cost, 2),
            'potential_savings': round(breakdown_cost - prevention_cost, 2),
            'roi_percentage': round(roi, 1),
            'cost_breakdown': {
                'prevention': self._get_prevention_breakdown(costs, failure_category),
                'breakdown': self._get_breakdown_breakdown(costs, failure_category)
            },
            'recommendation': self._generate_cost_recommendation(prevention_cost, breakdown_cost, risk_tier),
            'calculated_at': datetime.now().isoformat()
        }
    
    def _categorize_failure(self, failure_type, machine_type):
        """Categorize failure type based on description"""
        failure_type_lower = failure_type.lower()
        
        if machine_type == 'MRI':
            if 'helium' in failure_type_lower:
                return 'helium'
            elif 'gradient' in failure_type_lower or 'coil' in failure_type_lower:
                return 'gradient_coil'
            elif 'cool' in failure_type_lower:
                return 'cooling'
            elif 'magnet' in failure_type_lower:
                return 'magnet'
            else:
                return 'general'
        else:  # CT
            if 'tube' in failure_type_lower or 'x-ray' in failure_type_lower:
                return 'tube'
            elif 'cool' in failure_type_lower or 'oil' in failure_type_lower:
                return 'cooling'
            elif 'detector' in failure_type_lower:
                return 'detector'
            else:
                return 'general'
    
    def _calculate_prevention_cost(self, costs, failure_category):
        """Calculate cost of preventive maintenance"""
        # Map failure categories to preventive actions
        preventive_mapping = {
            'helium': 'helium_refill',
            'gradient_coil': 'gradient_coil_service',
            'cooling': 'cooling_system_service',
            'magnet': 'general_inspection',
            'general': 'general_inspection',
            'tube': 'tube_service',
            'detector': 'detector_calibration'
        }
        
        action = preventive_mapping.get(failure_category, 'general_inspection')
        parts_cost = costs['preventive'].get(action, 2000)
        
        labor_hours = self.labor_costs['average_repair_hours']['preventive']
        labor_cost = labor_hours * self.labor_costs['regular_hourly']
        
        subtotal = parts_cost + labor_cost
        overhead = subtotal * self.additional_costs['administrative_overhead']
        
        return subtotal + overhead
    
    def _calculate_breakdown_cost(self, costs, failure_category, risk_tier):
        """Calculate cost of equipment breakdown"""
        # Map failure categories to emergency repairs
        emergency_mapping = {
            'helium': 'helium_emergency',
            'gradient_coil': 'gradient_coil_replacement',
            'cooling': 'cooling_system_replacement',
            'magnet': 'magnet_quench_recovery',
            'general': 'emergency_callout',
            'tube': 'tube_replacement',
            'detector': 'detector_replacement'
        }
        
        action = emergency_mapping.get(failure_category, 'emergency_callout')
        parts_cost = costs['emergency'].get(action, 10000)
        parts_cost *= (1 + self.additional_costs['parts_markup'])  # Emergency markup
        
        # Labor costs (emergency rates)
        labor_hours = self.labor_costs['average_repair_hours']['emergency']
        labor_cost = labor_hours * self.labor_costs['emergency_hourly']
        
        # Downtime costs
        if risk_tier == 'critical':
            downtime_hours = 48  # 2 days
        elif risk_tier == 'schedule_maintenance':
            downtime_hours = 24  # 1 day
        else:
            downtime_hours = 8
        
        downtime_cost = downtime_hours * costs['downtime_cost_per_hour']
        
        # Lost scan revenue
        lost_scans = (downtime_hours / 24) * costs['average_scans_per_day']
        lost_revenue = lost_scans * costs['revenue_per_scan']
        
        # Patient rescheduling costs
        rescheduling_cost = lost_scans * self.additional_costs['patient_rescheduling_per_patient']
        
        subtotal = parts_cost + labor_cost + downtime_cost + lost_revenue + rescheduling_cost
        overhead = subtotal * self.additional_costs['administrative_overhead']
        
        return subtotal + overhead
    
    def _get_prevention_breakdown(self, costs, failure_category):
        """Get detailed breakdown of prevention costs"""
        preventive_mapping = {
            'helium': 'helium_refill',
            'gradient_coil': 'gradient_coil_service',
            'cooling': 'cooling_system_service',
            'magnet': 'general_inspection',
            'general': 'general_inspection',
            'tube': 'tube_service',
            'detector': 'detector_calibration'
        }
        
        action = preventive_mapping.get(failure_category, 'general_inspection')
        parts_cost = costs['preventive'].get(action, 2000)
        
        labor_hours = self.labor_costs['average_repair_hours']['preventive']
        labor_cost = labor_hours * self.labor_costs['regular_hourly']
        
        return {
            'parts_and_materials': parts_cost,
            'labor': labor_cost,
            'labor_hours': labor_hours,
            'overhead': round((parts_cost + labor_cost) * self.additional_costs['administrative_overhead'], 2)
        }
    
    def _get_breakdown_breakdown(self, costs, failure_category):
        """Get detailed breakdown of potential breakdown costs"""
        emergency_mapping = {
            'helium': 'helium_emergency',
            'gradient_coil': 'gradient_coil_replacement',
            'cooling': 'cooling_system_replacement',
            'magnet': 'magnet_quench_recovery',
            'general': 'emergency_callout',
            'tube': 'tube_replacement',
            'detector': 'detector_replacement'
        }
        
        action = emergency_mapping.get(failure_category, 'emergency_callout')
        parts_cost = costs['emergency'].get(action, 10000)
        
        labor_hours = self.labor_costs['average_repair_hours']['emergency']
        labor_cost = labor_hours * self.labor_costs['emergency_hourly']
        
        downtime_hours = 24
        downtime_cost = downtime_hours * costs['downtime_cost_per_hour']
        
        lost_scans = costs['average_scans_per_day']
        lost_revenue = lost_scans * costs['revenue_per_scan']
        
        return {
            'parts_and_materials': round(parts_cost * (1 + self.additional_costs['parts_markup']), 2),
            'emergency_labor': labor_cost,
            'labor_hours': labor_hours,
            'downtime_cost': downtime_cost,
            'lost_revenue': lost_revenue,
            'patient_rescheduling': lost_scans * self.additional_costs['patient_rescheduling_per_patient']
        }
    
    def _generate_cost_recommendation(self, prevention_cost, breakdown_cost, risk_tier):
        """Generate recommendation based on cost analysis"""
        savings = breakdown_cost - prevention_cost
        roi = (savings / prevention_cost * 100) if prevention_cost > 0 else 0
        
        if risk_tier == 'critical':
            urgency = "IMMEDIATE ACTION REQUIRED"
        elif risk_tier == 'schedule_maintenance':
            urgency = "Schedule maintenance within 14 days"
        else:
            urgency = "Monitor and plan maintenance"
        
        return {
            'urgency': urgency,
            'savings_potential': f"${savings:,.2f}",
            'roi': f"{roi:.1f}%",
            'recommendation': f"Preventive maintenance at ${prevention_cost:,.2f} could save up to ${savings:,.2f} compared to potential breakdown costs of ${breakdown_cost:,.2f}."
        }
    
    def calculate_energy_savings(self, machine_type, eco_hours, deep_sleep_hours):
        """Calculate energy savings from eco/sleep modes"""
        energy_rates = {
            'MRI': {
                'ready_kwh': 25,  # kWh per hour in ready mode
                'eco_kwh': 12,
                'deep_sleep_kwh': 3,
                'cost_per_kwh': 0.12
            },
            'CT': {
                'ready_kwh': 15,
                'eco_kwh': 6,
                'deep_sleep_kwh': 1.5,
                'cost_per_kwh': 0.12
            }
        }
        
        rates = energy_rates.get(machine_type, energy_rates['MRI'])
        
        # Calculate savings
        eco_savings_kwh = (rates['ready_kwh'] - rates['eco_kwh']) * eco_hours
        sleep_savings_kwh = (rates['ready_kwh'] - rates['deep_sleep_kwh']) * deep_sleep_hours
        
        total_savings_kwh = eco_savings_kwh + sleep_savings_kwh
        cost_savings = total_savings_kwh * rates['cost_per_kwh']
        
        return {
            'eco_mode_savings_kwh': round(eco_savings_kwh, 2),
            'deep_sleep_savings_kwh': round(sleep_savings_kwh, 2),
            'total_savings_kwh': round(total_savings_kwh, 2),
            'cost_savings': round(cost_savings, 2),
            'co2_reduction_kg': round(total_savings_kwh * 0.4, 2)  # Approx 0.4 kg CO2 per kWh
        }