# ml_models.py
import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import joblib
import os
import json
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')


class AnomalyDetector:
    """Isolation Forest based anomaly detection"""
    
    def __init__(self):
        self.models = {}
        self.scalers = {}
        self.feature_columns = {
            'MRI': ['Component_Temp', 'Gradient_Coil_Temp', 'Vibration_Level', 
                   'Cooling_System_Performance', 'Magnet_Temp_K', 'Helium_Level', 'Helium_Pressure_psi'],
            'CT': ['Component_Temp', 'Gradient_Coil_Temp', 'Vibration_Level',
                  'Cooling_System_Performance', 'X_ray_Tube_Temp', 'Cooling_Oil_Temp']
        }
        self.is_trained = False
        self.means = {}
        self.thresholds = {}
    
    def train(self, data_path):
        """Train Isolation Forest models on historical data"""
        print("Training Anomaly Detection Models (Isolation Forest)...")
        
        os.makedirs('models', exist_ok=True)
        
        df = pd.read_csv(data_path)
        print(f"Loaded {len(df)} records for training")
        print(f"Available columns: {list(df.columns)}")
        
        df = self._clean_dataframe(df)
        
        for machine_type in ['MRI', 'CT']:
            machine_data = df[df['Machine_Type'] == machine_type].copy()
            
            if len(machine_data) == 0:
                print(f"Warning: No {machine_type} data found")
                continue
            
            features = self.feature_columns[machine_type]
            available_features = [f for f in features if f in machine_data.columns]
            
            if len(available_features) == 0:
                print(f"Warning: No features available for {machine_type}")
                continue
            
            X = machine_data[available_features].copy()
            
            # Store statistics for later use
            self.means[machine_type] = X.mean().to_dict()
            self.thresholds[machine_type] = {
                'mean': X.mean().to_dict(),
                'std': X.std().to_dict(),
                'min': X.min().to_dict(),
                'max': X.max().to_dict()
            }
            
            X = X.fillna(X.mean())
            
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)
            
            if np.any(np.isnan(X_scaled)) or np.any(np.isinf(X_scaled)):
                X_scaled = np.nan_to_num(X_scaled, nan=0.0, posinf=0.0, neginf=0.0)
            
            model = IsolationForest(
                n_estimators=100,
                contamination=0.1,
                max_samples='auto',
                random_state=42,
                n_jobs=-1
            )
            model.fit(X_scaled)
            
            self.models[machine_type] = model
            self.scalers[machine_type] = scaler
            self.feature_columns[machine_type] = available_features
            
            print(f"✓ {machine_type} anomaly model trained with {len(available_features)} features")
        
        self.is_trained = True
        print("Anomaly Detection Models trained successfully!")
        self.save_models()
    
    def _clean_dataframe(self, df):
        """Clean dataframe by handling NaN and invalid values"""
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        
        for col in numeric_cols:
            df[col] = df[col].replace([np.inf, -np.inf], np.nan)
            median_val = df[col].median()
            if pd.isna(median_val):
                median_val = 0
            df[col] = df[col].fillna(median_val)
        
        return df
    
    def detect_anomalies(self, readings, machine_type):
        """Detect anomalies in current readings"""
        if not self.is_trained or machine_type not in self.models:
            return {'is_anomaly': False, 'anomaly_score': 0, 'flagged_parameters': []}
        
        features = self.feature_columns[machine_type]
        
        X_values = []
        for f in features:
            val = readings.get(f, 0)
            if val is None or (isinstance(val, float) and np.isnan(val)):
                val = self.means.get(machine_type, {}).get(f, 0)
            X_values.append(float(val) if val is not None else 0.0)
        
        X = np.array([X_values])
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        
        try:
            X_scaled = self.scalers[machine_type].transform(X)
            
            if np.any(np.isnan(X_scaled)) or np.any(np.isinf(X_scaled)):
                X_scaled = np.nan_to_num(X_scaled, nan=0.0, posinf=0.0, neginf=0.0)
            
            prediction = self.models[machine_type].predict(X_scaled)[0]
            anomaly_score = -self.models[machine_type].score_samples(X_scaled)[0]
            
            # Normalize score to 0-1 range
            anomaly_score = min(max((anomaly_score + 0.5) / 1.0, 0), 1)
            
            flagged_parameters = []
            if prediction == -1:
                for i, feature in enumerate(features):
                    val = readings.get(feature)
                    if val is not None:
                        mean = self.scalers[machine_type].mean_[i]
                        std = self.scalers[machine_type].scale_[i]
                        if std > 0:
                            z_score = abs((float(val) - mean) / std)
                            if z_score > 2:
                                flagged_parameters.append({
                                    'parameter': feature,
                                    'value': float(val),
                                    'expected_mean': round(float(mean), 2),
                                    'z_score': round(float(z_score), 2),
                                    'severity': 'high' if z_score > 3 else 'medium'
                                })
            
            return {
                'is_anomaly': prediction == -1,
                'anomaly_score': round(float(anomaly_score), 4),
                'flagged_parameters': flagged_parameters
            }
        except Exception as e:
            print(f"Error in anomaly detection: {e}")
            return {'is_anomaly': False, 'anomaly_score': 0, 'flagged_parameters': []}
    
    def save_models(self, path='models/'):
        """Save trained models"""
        os.makedirs(path, exist_ok=True)
        
        for machine_type in self.models:
            joblib.dump(self.models[machine_type], f'{path}anomaly_{machine_type}.joblib')
            joblib.dump(self.scalers[machine_type], f'{path}scaler_anomaly_{machine_type}.joblib')
        
        with open(f'{path}feature_columns.json', 'w') as f:
            json.dump(self.feature_columns, f)
        
        with open(f'{path}anomaly_means.json', 'w') as f:
            json.dump(self.means, f)
        
        with open(f'{path}anomaly_thresholds.json', 'w') as f:
            json.dump(self.thresholds, f)
        
        print(f"Models saved to {path}")
    
    def load_models(self, path='models/'):
        """Load saved models"""
        try:
            for machine_type in ['MRI', 'CT']:
                model_path = f'{path}anomaly_{machine_type}.joblib'
                scaler_path = f'{path}scaler_anomaly_{machine_type}.joblib'
                
                if os.path.exists(model_path) and os.path.exists(scaler_path):
                    self.models[machine_type] = joblib.load(model_path)
                    self.scalers[machine_type] = joblib.load(scaler_path)
            
            fc_path = f'{path}feature_columns.json'
            if os.path.exists(fc_path):
                with open(fc_path, 'r') as f:
                    self.feature_columns = json.load(f)
            
            means_path = f'{path}anomaly_means.json'
            if os.path.exists(means_path):
                with open(means_path, 'r') as f:
                    self.means = json.load(f)
            
            thresholds_path = f'{path}anomaly_thresholds.json'
            if os.path.exists(thresholds_path):
                with open(thresholds_path, 'r') as f:
                    self.thresholds = json.load(f)
            
            self.is_trained = len(self.models) > 0
            
            if self.is_trained:
                print(f"Loaded {len(self.models)} anomaly detection models")
            
            return self.is_trained
        except Exception as e:
            print(f"Error loading models: {e}")
            return False


class FailurePredictor:
    """Random Forest based failure prediction"""
    
    def __init__(self):
        self.models = {}
        self.scalers = {}
        self.feature_columns = {}
        self.is_trained = False
        self.means = {}
        self.thresholds = {}
        self.num_classes = {}
    
    def prepare_features(self, df, machine_type):
        """Prepare features for training"""
        feature_cols = ['Component_Temp', 'Gradient_Coil_Temp', 'Vibration_Level', 'Cooling_System_Performance']
        
        if machine_type == 'MRI':
            feature_cols.extend(['Magnet_Temp_K', 'Helium_Level', 'Helium_Pressure_psi'])
        else:
            feature_cols.extend(['X_ray_Tube_Temp', 'Cooling_Oil_Temp'])
        
        available_cols = [c for c in feature_cols if c in df.columns]
        return available_cols
    
    def _calculate_severity_level(self, row, thresholds):
        """Calculate severity level based on sensor readings using percentile-based thresholds"""
        severity_score = 0
        num_checks = 0
        
        # Check cooling system (lower is worse)
        cooling = row.get('Cooling_System_Performance')
        if pd.notna(cooling):
            num_checks += 1
            cooling_threshold = thresholds.get('Cooling_System_Performance', {})
            p25 = cooling_threshold.get('p25', 85)
            p10 = cooling_threshold.get('p10', 75)
            if cooling < p10:
                severity_score += 2
            elif cooling < p25:
                severity_score += 1
        
        # Check gradient coil temp (higher is worse)
        gradient = row.get('Gradient_Coil_Temp')
        if pd.notna(gradient):
            num_checks += 1
            gradient_threshold = thresholds.get('Gradient_Coil_Temp', {})
            p75 = gradient_threshold.get('p75', 55)
            p90 = gradient_threshold.get('p90', 65)
            if gradient > p90:
                severity_score += 2
            elif gradient > p75:
                severity_score += 1
        
        # Check vibration (higher is worse)
        vibration = row.get('Vibration_Level')
        if pd.notna(vibration):
            num_checks += 1
            vibration_threshold = thresholds.get('Vibration_Level', {})
            p75 = vibration_threshold.get('p75', 2.5)
            p90 = vibration_threshold.get('p90', 3.5)
            if vibration > p90:
                severity_score += 2
            elif vibration > p75:
                severity_score += 1
        
        # Check component temp (higher is worse)
        comp_temp = row.get('Component_Temp')
        if pd.notna(comp_temp):
            num_checks += 1
            comp_threshold = thresholds.get('Component_Temp', {})
            p75 = comp_threshold.get('p75', 40)
            p90 = comp_threshold.get('p90', 50)
            if comp_temp > p90:
                severity_score += 2
            elif comp_temp > p75:
                severity_score += 1
        
        # MRI specific checks
        if row.get('Machine_Type') == 'MRI':
            helium = row.get('Helium_Level')
            if pd.notna(helium):
                num_checks += 1
                helium_threshold = thresholds.get('Helium_Level', {})
                p25 = helium_threshold.get('p25', 85)
                p10 = helium_threshold.get('p10', 75)
                if helium < p10:
                    severity_score += 2
                elif helium < p25:
                    severity_score += 1
            
            magnet_temp = row.get('Magnet_Temp_K')
            if pd.notna(magnet_temp):
                num_checks += 1
                magnet_threshold = thresholds.get('Magnet_Temp_K', {})
                p75 = magnet_threshold.get('p75', 4.2)
                p90 = magnet_threshold.get('p90', 4.5)
                if magnet_temp > p90:
                    severity_score += 2
                elif magnet_temp > p75:
                    severity_score += 1
        
        # CT specific checks
        else:
            tube_temp = row.get('X_ray_Tube_Temp')
            if pd.notna(tube_temp):
                num_checks += 1
                tube_threshold = thresholds.get('X_ray_Tube_Temp', {})
                p75 = tube_threshold.get('p75', 65)
                p90 = tube_threshold.get('p90', 80)
                if tube_temp > p90:
                    severity_score += 2
                elif tube_temp > p75:
                    severity_score += 1
            
            oil_temp = row.get('Cooling_Oil_Temp')
            if pd.notna(oil_temp):
                num_checks += 1
                oil_threshold = thresholds.get('Cooling_Oil_Temp', {})
                p75 = oil_threshold.get('p75', 45)
                p90 = oil_threshold.get('p90', 55)
                if oil_temp > p90:
                    severity_score += 2
                elif oil_temp > p75:
                    severity_score += 1
        
        # Error code check
        error_code = row.get('Error_Code', 'E000')
        if pd.notna(error_code) and str(error_code) != 'E000':
            if str(error_code).startswith('E5') or str(error_code).startswith('E6'):
                severity_score += 3
            elif str(error_code).startswith('E1') or str(error_code).startswith('E2'):
                severity_score += 1
        
        # Normalize severity
        if num_checks == 0:
            return 0
        
        avg_score = severity_score / num_checks
        
        if avg_score >= 1.5:
            return 5  # Critical
        elif avg_score >= 0.5:
            return 3  # Warning
        else:
            return 0  # Normal
    
    def _compute_thresholds(self, df):
        """Compute percentile thresholds from data"""
        thresholds = {}
        numeric_cols = ['Component_Temp', 'Gradient_Coil_Temp', 'Vibration_Level', 
                       'Cooling_System_Performance', 'Magnet_Temp_K', 'Helium_Level', 
                       'Helium_Pressure_psi', 'X_ray_Tube_Temp', 'Cooling_Oil_Temp']
        
        for col in numeric_cols:
            if col in df.columns:
                data = df[col].dropna()
                if len(data) > 0:
                    thresholds[col] = {
                        'p10': float(data.quantile(0.10)),
                        'p25': float(data.quantile(0.25)),
                        'p50': float(data.quantile(0.50)),
                        'p75': float(data.quantile(0.75)),
                        'p90': float(data.quantile(0.90)),
                        'mean': float(data.mean()),
                        'std': float(data.std())
                    }
        
        return thresholds
    
    def train(self, data_path):
        """Train Random Forest models for failure prediction"""
        print("Training Failure Prediction Models (Random Forest)...")
        
        os.makedirs('models', exist_ok=True)
        
        df = pd.read_csv(data_path)
        df = self._clean_dataframe(df)
        
        print(f"Columns in dataset: {list(df.columns)}")
        
        # Compute thresholds from data
        self.thresholds = self._compute_thresholds(df)
        
        # Create Severity_Level if it doesn't exist
        if 'Severity_Level' not in df.columns:
            print("Severity_Level column not found. Calculating from sensor readings...")
            df['Severity_Level'] = df.apply(lambda row: self._calculate_severity_level(row, self.thresholds), axis=1)
            severity_dist = df['Severity_Level'].value_counts().to_dict()
            print(f"Calculated Severity_Level distribution: {severity_dist}")
        
        # Create target variable - ensure we have all 3 classes
        def map_severity_to_risk(severity):
            if pd.isna(severity):
                return 0
            if severity == 0:
                return 0  # Normal
            elif severity == 3:
                return 1  # Monitor
            elif severity == 5:
                return 2  # Critical
            return 0
        
        df['risk_level'] = df['Severity_Level'].apply(map_severity_to_risk)
        
        for machine_type in ['MRI', 'CT']:
            machine_data = df[df['Machine_Type'] == machine_type].copy()
            
            if len(machine_data) == 0:
                print(f"Warning: No {machine_type} data found")
                continue
            
            feature_cols = self.prepare_features(machine_data, machine_type)
            self.feature_columns[machine_type] = feature_cols
            
            X = machine_data[feature_cols].copy()
            
            self.means[machine_type] = X.mean().to_dict()
            
            X = X.fillna(X.mean())
            
            y = machine_data['risk_level'].fillna(0).astype(int)
            
            # Ensure we have samples of each class for balanced training
            unique_classes = y.unique()
            print(f"  {machine_type} - Classes in data: {sorted(unique_classes)}, Distribution: {y.value_counts().to_dict()}")
            
            # Store number of classes
            self.num_classes[machine_type] = len(unique_classes)
            
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)
            X_scaled = np.nan_to_num(X_scaled, nan=0.0, posinf=0.0, neginf=0.0)
            
            model = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                min_samples_split=5,
                min_samples_leaf=2,
                random_state=42,
                n_jobs=-1,
                class_weight='balanced'
            )
            model.fit(X_scaled, y)
            
            self.models[machine_type] = model
            self.scalers[machine_type] = scaler
            
            print(f"✓ {machine_type} failure predictor trained with {len(unique_classes)} classes")
        
        self.is_trained = True
        print("Failure Prediction Models trained successfully!")
        self.save_models()
    
    def _clean_dataframe(self, df):
        """Clean dataframe"""
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        
        for col in numeric_cols:
            df[col] = df[col].replace([np.inf, -np.inf], np.nan)
            median_val = df[col].median()
            if pd.isna(median_val):
                median_val = 0
            df[col] = df[col].fillna(median_val)
        
        return df
    
    def predict_failure_risk(self, readings, machine_type, anomaly_report=None):
        """Predict failure risk based on current readings"""
        if not self.is_trained or machine_type not in self.models:
            return {
                'risk_tier': 'normal',
                'risk_score': 0,
                'confidence': 0,
                'failure_probability': 0,
                'predicted_days_to_failure': None,
                'reasoning': 'Model not trained'
            }
        
        features = self.feature_columns[machine_type]
        
        X_values = []
        for f in features:
            val = readings.get(f, 0)
            if val is None or (isinstance(val, float) and np.isnan(val)):
                val = self.means.get(machine_type, {}).get(f, 0)
            X_values.append(float(val) if val is not None else 0.0)
        
        X = np.array([X_values])
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        
        try:
            X_scaled = self.scalers[machine_type].transform(X)
            X_scaled = np.nan_to_num(X_scaled, nan=0.0, posinf=0.0, neginf=0.0)
            
            prediction = self.models[machine_type].predict(X_scaled)[0]
            probabilities = self.models[machine_type].predict_proba(X_scaled)[0]
            
            # Get actual classes from the model
            classes = self.models[machine_type].classes_
            num_classes = len(classes)
            
            # Calculate risk score based on actual number of classes
            if num_classes == 3:
                weights = np.array([0, 0.5, 1.0])
            elif num_classes == 2:
                if 0 in classes and 2 in classes:
                    weights = np.array([0, 1.0])
                elif 0 in classes and 1 in classes:
                    weights = np.array([0, 0.5])
                else:
                    weights = np.array([0.5, 1.0])
            else:
                weights = np.linspace(0, 1, num_classes)
            
            risk_score = float(np.sum(probabilities * weights))
            
            # Adjust based on anomaly report
            if anomaly_report and anomaly_report.get('is_anomaly'):
                risk_score = min(risk_score + anomaly_report.get('anomaly_score', 0) * 0.3, 1.0)
            
            # Check sensor values directly
            risk_score = self._adjust_risk_from_readings(readings, machine_type, risk_score)
            
            # Determine risk tier
            if risk_score >= 0.85:
                risk_tier = 'critical'
                predicted_days = 0
            elif risk_score >= 0.65:
                risk_tier = 'schedule_maintenance'
                predicted_days = int((1 - risk_score) * 30)
            elif risk_score >= 0.40:
                risk_tier = 'monitor'
                predicted_days = int((1 - risk_score) * 60)
            else:
                risk_tier = 'normal'
                predicted_days = None
            
            reasoning = self._generate_reasoning(readings, features, machine_type, risk_tier, anomaly_report)
            confidence = float(max(probabilities)) * 100
            
            # Get failure probability (highest risk class)
            max_class_idx = len(classes) - 1
            failure_prob = float(probabilities[max_class_idx]) * 100 if max_class_idx < len(probabilities) else 0
            
            return {
                'risk_tier': risk_tier,
                'risk_score': round(float(risk_score), 4),
                'confidence': round(confidence, 2),
                'failure_probability': round(failure_prob, 2),
                'predicted_days_to_failure': predicted_days,
                'reasoning': reasoning,
                'feature_importances': self._get_feature_importances(machine_type)
            }
        except Exception as e:
            print(f"Error in failure prediction: {e}")
            import traceback
            traceback.print_exc()
            return {
                'risk_tier': 'normal',
                'risk_score': 0,
                'confidence': 0,
                'failure_probability': 0,
                'predicted_days_to_failure': None,
                'reasoning': f'Prediction error: {str(e)}'
            }
    
    def _adjust_risk_from_readings(self, readings, machine_type, base_risk):
        """Adjust risk score based on direct sensor value checks"""
        risk_adjustment = 0
        
        # Cooling system check
        cooling = readings.get('Cooling_System_Performance', 100)
        if cooling is not None:
            if cooling < 75:
                risk_adjustment += 0.3
            elif cooling < 85:
                risk_adjustment += 0.15
        
        # Gradient coil temp check
        gradient = readings.get('Gradient_Coil_Temp', 45)
        if gradient is not None:
            if gradient > 70:
                risk_adjustment += 0.3
            elif gradient > 60:
                risk_adjustment += 0.15
        
        # Vibration check
        vibration = readings.get('Vibration_Level', 1.5)
        if vibration is not None:
            if vibration > 4:
                risk_adjustment += 0.25
            elif vibration > 3:
                risk_adjustment += 0.1
        
        # MRI specific
        if machine_type == 'MRI':
            helium = readings.get('Helium_Level', 100)
            if helium is not None:
                if helium < 70:
                    risk_adjustment += 0.4
                elif helium < 80:
                    risk_adjustment += 0.2
            
            magnet = readings.get('Magnet_Temp_K', 4.0)
            if magnet is not None:
                if magnet > 4.5:
                    risk_adjustment += 0.3
                elif magnet > 4.3:
                    risk_adjustment += 0.15
        
        # CT specific
        else:
            tube = readings.get('X_ray_Tube_Temp', 50)
            if tube is not None:
                if tube > 85:
                    risk_adjustment += 0.35
                elif tube > 75:
                    risk_adjustment += 0.15
        
        # Error code check
        error_code = readings.get('Error_Code', 'E000')
        if error_code and str(error_code) != 'E000':
            if str(error_code).startswith('E5') or str(error_code).startswith('E6'):
                risk_adjustment += 0.3
            elif str(error_code).startswith('E1') or str(error_code).startswith('E2'):
                risk_adjustment += 0.1
        
        return min(base_risk + risk_adjustment, 1.0)
    
    def _generate_reasoning(self, readings, features, machine_type, risk_tier, anomaly_report):
        """Generate human-readable reasoning"""
        reasons = []
        
        if anomaly_report and anomaly_report.get('flagged_parameters'):
            for param in anomaly_report['flagged_parameters']:
                reasons.append(f"{param['parameter']}: {param['value']} (expected ~{param['expected_mean']})")
        
        # MRI specific checks
        if machine_type == 'MRI':
            helium = readings.get('Helium_Level')
            if helium is not None and helium < 80:
                reasons.append(f"Low helium level: {helium}%")
            magnet_temp = readings.get('Magnet_Temp_K')
            if magnet_temp is not None and magnet_temp > 4.3:
                reasons.append(f"Elevated magnet temperature: {magnet_temp}K")
        
        # CT specific checks
        if machine_type == 'CT':
            tube_temp = readings.get('X_ray_Tube_Temp')
            if tube_temp is not None and tube_temp > 75:
                reasons.append(f"High X-ray tube temperature: {tube_temp}°C")
        
        # Common checks
        gradient = readings.get('Gradient_Coil_Temp')
        if gradient is not None and gradient > 60:
            reasons.append(f"High gradient coil temperature: {gradient}°C")
        
        vibration = readings.get('Vibration_Level')
        if vibration is not None and vibration > 3:
            reasons.append(f"Elevated vibration level: {vibration} mm/s")
        
        cooling = readings.get('Cooling_System_Performance')
        if cooling is not None and cooling < 85:
            reasons.append(f"Degraded cooling performance: {cooling}%")
        
        error_code = readings.get('Error_Code')
        if error_code and str(error_code) != 'E000':
            reasons.append(f"Error code detected: {error_code}")
        
        if not reasons:
            if risk_tier == 'normal':
                reasons.append("All parameters within normal operating ranges")
            else:
                reasons.append("Multiple parameters showing slight deviation from baseline")
        
        return '; '.join(reasons)
    
    def _get_feature_importances(self, machine_type):
        """Get feature importances"""
        if machine_type not in self.models:
            return {}
        
        importances = self.models[machine_type].feature_importances_
        features = self.feature_columns[machine_type]
        
        return {f: round(float(imp), 4) for f, imp in zip(features, importances)}
    
    def save_models(self, path='models/'):
        """Save trained models"""
        os.makedirs(path, exist_ok=True)
        
        for machine_type in self.models:
            joblib.dump(self.models[machine_type], f'{path}predictor_{machine_type}.joblib')
            joblib.dump(self.scalers[machine_type], f'{path}scaler_predictor_{machine_type}.joblib')
        
        with open(f'{path}predictor_features.json', 'w') as f:
            json.dump(self.feature_columns, f)
        
        with open(f'{path}predictor_means.json', 'w') as f:
            json.dump(self.means, f)
        
        with open(f'{path}predictor_thresholds.json', 'w') as f:
            json.dump(self.thresholds, f)
        
        with open(f'{path}predictor_num_classes.json', 'w') as f:
            json.dump(self.num_classes, f)
        
        print(f"Predictor models saved to {path}")
    
    def load_models(self, path='models/'):
        """Load saved models"""
        try:
            for machine_type in ['MRI', 'CT']:
                model_path = f'{path}predictor_{machine_type}.joblib'
                scaler_path = f'{path}scaler_predictor_{machine_type}.joblib'
                
                if os.path.exists(model_path) and os.path.exists(scaler_path):
                    self.models[machine_type] = joblib.load(model_path)
                    self.scalers[machine_type] = joblib.load(scaler_path)
            
            fc_path = f'{path}predictor_features.json'
            if os.path.exists(fc_path):
                with open(fc_path, 'r') as f:
                    self.feature_columns = json.load(f)
            
            means_path = f'{path}predictor_means.json'
            if os.path.exists(means_path):
                with open(means_path, 'r') as f:
                    self.means = json.load(f)
            
            thresholds_path = f'{path}predictor_thresholds.json'
            if os.path.exists(thresholds_path):
                with open(thresholds_path, 'r') as f:
                    self.thresholds = json.load(f)
            
            num_classes_path = f'{path}predictor_num_classes.json'
            if os.path.exists(num_classes_path):
                with open(num_classes_path, 'r') as f:
                    self.num_classes = json.load(f)
            
            self.is_trained = len(self.models) > 0
            
            if self.is_trained:
                print(f"Loaded {len(self.models)} failure prediction models")
            
            return self.is_trained
        except Exception as e:
            print(f"Error loading predictor models: {e}")
            return False


class BaselineComputer:
    """Computes operational baselines for machines"""
    
    def __init__(self):
        self.baselines = {}
    
    def compute_baseline(self, telemetry_data, machine_id, lookback_days=30):
        """Compute baseline operating ranges from historical data"""
        if len(telemetry_data) == 0:
            return self._get_default_baseline()
        
        baseline = {}
        numeric_columns = telemetry_data.select_dtypes(include=[np.number]).columns
        
        for col in numeric_columns:
            data = telemetry_data[col].dropna()
            if len(data) > 0:
                baseline[col] = {
                    'mean': round(float(data.mean()), 4),
                    'std': round(float(data.std()), 4) if data.std() > 0 else 1.0,
                    'min': round(float(data.min()), 4),
                    'max': round(float(data.max()), 4),
                    'percentile_5': round(float(data.quantile(0.05)), 4),
                    'percentile_95': round(float(data.quantile(0.95)), 4)
                }
        
        self.baselines[machine_id] = baseline
        return baseline
    
    def _get_default_baseline(self):
        """Return default baseline values"""
        return {
            'Component_Temp': {'mean': 35, 'std': 5, 'min': 25, 'max': 50},
            'Gradient_Coil_Temp': {'mean': 45, 'std': 8, 'min': 30, 'max': 65},
            'Vibration_Level': {'mean': 1.5, 'std': 0.5, 'min': 0.5, 'max': 3.0},
            'Cooling_System_Performance': {'mean': 95, 'std': 3, 'min': 85, 'max': 100},
            'Magnet_Temp_K': {'mean': 4.0, 'std': 0.2, 'min': 3.5, 'max': 4.5},
            'Helium_Level': {'mean': 90, 'std': 5, 'min': 75, 'max': 100},
            'Helium_Pressure_psi': {'mean': 16, 'std': 1, 'min': 14, 'max': 18},
            'X_ray_Tube_Temp': {'mean': 55, 'std': 10, 'min': 40, 'max': 80},
            'Cooling_Oil_Temp': {'mean': 40, 'std': 5, 'min': 30, 'max': 55}
        }
    
    def check_deviation(self, current_readings, machine_id):
        """Check deviation from baseline"""
        if machine_id not in self.baselines:
            self.baselines[machine_id] = self._get_default_baseline()
        
        baseline = self.baselines[machine_id]
        deviations = []
        
        for param, value in current_readings.items():
            if param in baseline and value is not None:
                try:
                    value = float(value)
                    if np.isnan(value):
                        continue
                    
                    b = baseline[param]
                    mean = b.get('mean', 0)
                    std = b.get('std', 1)
                    
                    if std > 0:
                        z_score = (value - mean) / std
                        if abs(z_score) > 2:
                            deviations.append({
                                'parameter': param,
                                'current_value': round(float(value), 2),
                                'baseline_mean': round(float(mean), 2),
                                'z_score': round(float(z_score), 2),
                                'deviation_type': 'high' if z_score > 0 else 'low'
                            })
                except (ValueError, TypeError):
                    continue
        
        return {
            'deviation_detected': len(deviations) > 0,
            'deviations': deviations
        }


class MLModelManager:
    """Manager for all ML models"""
    
    def __init__(self):
        self.anomaly_detector = AnomalyDetector()
        self.failure_predictor = FailurePredictor()
        self.baseline_computer = BaselineComputer()
        self.is_initialized = False
    
    def initialize(self, data_path):
        """Initialize and train all models"""
        os.makedirs('models', exist_ok=True)
        
        # Always train fresh to ensure consistency
        if os.path.exists(data_path):
            print(f"Training models from {data_path}...")
            
            # Delete old models to ensure fresh training
            self._clear_old_models()
            
            self.anomaly_detector.train(data_path)
            self.failure_predictor.train(data_path)
            
            # Compute baselines
            df = pd.read_csv(data_path)
            for machine_type in ['MRI', 'CT']:
                machine_data = df[df['Machine_Type'] == machine_type]
                machine_id = f'{machine_type}-001'
                self.baseline_computer.compute_baseline(machine_data, machine_id)
            
            self.is_initialized = True
            print("✓ All models initialized successfully")
            return True
        else:
            print(f"Warning: Dataset not found at {data_path}")
            # Use default baselines
            self.baseline_computer.baselines['MRI-001'] = self.baseline_computer._get_default_baseline()
            self.baseline_computer.baselines['CT-001'] = self.baseline_computer._get_default_baseline()
            return False
    
    def _clear_old_models(self):
        """Clear old model files"""
        import glob
        for f in glob.glob('models/*.joblib'):
            try:
                os.remove(f)
            except:
                pass
        for f in glob.glob('models/*.json'):
            try:
                os.remove(f)
            except:
                pass
    
    def analyze_readings(self, readings, machine_type, machine_id):
        """Full analysis of current readings"""
        anomaly_report = self.anomaly_detector.detect_anomalies(readings, machine_type)
        risk_report = self.failure_predictor.predict_failure_risk(readings, machine_type, anomaly_report)
        deviation_report = self.baseline_computer.check_deviation(readings, machine_id)
        
        return {
            'anomaly_report': anomaly_report,
            'risk_report': risk_report,
            'deviation_report': deviation_report,
            'timestamp': datetime.now().isoformat()
        }