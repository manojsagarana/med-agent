import os
from datetime import timedelta

class Config:
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'predictive-maintenance-agent-secret-key-2024'
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///maintenance_agent.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Email settings (Update with your credentials)
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = 'giridhareshwaran2005@gmail.com'
    MAIL_PASSWORD = 'aejr rflw kzjo brcd'
    MAIL_DEFAULT_SENDER = 'giridhareshwaran2005@gmail.com'
    
    # SMS via SMTP (email-to-SMS gateway)
    # Example domains (carrier-specific): txt.att.net, vtext.com, tmomail.net, etc.
    # Set this in your environment to whatever gateway you want to use.
    SMS_GATEWAY_DOMAIN = os.environ.get('SMS_GATEWAY_DOMAIN')
    # If no gateway is configured, optionally fall back to vendor email.
    SMS_FALLBACK_TO_VENDOR_EMAIL = (os.environ.get('SMS_FALLBACK_TO_VENDOR_EMAIL', 'true').lower() == 'true')
    
    # Vendor API endpoints (simulated)
    VENDOR_API_BASE_URL = 'http://localhost:5000/api/vendor'
    
    # Telemetry settings
    TELEMETRY_UPDATE_INTERVAL = 5  # seconds
    BASELINE_LOOKBACK_DAYS = 30
    
    # Alert thresholds
    FAILURE_PREDICTION_WINDOW_DAYS = 14
    CRITICAL_THRESHOLD = 0.85
    SCHEDULE_MAINTENANCE_THRESHOLD = 0.65
    MONITOR_THRESHOLD = 0.40
    
    # Session settings
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    
    # Default credentials
    DEFAULT_ADMIN_USERNAME = 'admin'
    DEFAULT_ADMIN_PASSWORD = 'admin123'
    DEFAULT_ENGINEER_USERNAME = 'engineer'
    DEFAULT_ENGINEER_PASSWORD = 'engineer123'


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}