// static/js/dashboard.js

// Configuration
const API_BASE = '/api';
let socket = null;
let telemetryChart = null;
let chartData = {
    labels: [],
    datasets: []
};
let currentChartMachine = 'mri_brain_01';

// All machine IDs
const MACHINE_IDS = ['mri_brain_01', 'mri_spine_01', 'mri_msk_01', 'ct_chest_01', 'ct_abdo_01'];

// Initialize Dashboard
function initDashboard() {
    initSocket();
    initChart();
    loadDashboardData();
    
    // Set up auto-refresh
    setInterval(loadDashboardData, 10000);
    
    // Chart machine selector
    const chartSelect = document.getElementById('chart-machine-select');
    if (chartSelect) {
        chartSelect.addEventListener('change', function() {
            currentChartMachine = this.value;
            loadMachineTelemetry(currentChartMachine);
        });
    }
}

// Socket.IO Connection
function initSocket() {
    socket = io();
    
    socket.on('connect', () => {
        console.log('Connected to server');
        updateConnectionStatus(true);
    });
    
    socket.on('disconnect', () => {
        console.log('Disconnected from server');
        updateConnectionStatus(false);
    });
    
    socket.on('telemetry_update', (data) => {
        updateMachineCard(data.machine_id, data.readings);
        if (data.machine_id === currentChartMachine) {
            updateChartData(data.readings);
        }
    });
    
    socket.on('analysis_started', (data) => {
        showAnalysisBanner(data.machine_id, 'started');
        markMachineAnalyzing(data.machine_id, true);
    });
    
    socket.on('analysis_complete', (data) => {
        showAnalysisBanner(data.machine_id, 'complete');
        markMachineAnalyzing(data.machine_id, false);
        loadDashboardData();
        showToast(`Analysis complete for ${data.machine_id}`, 'success');
    });
    
    socket.on('analysis_error', (data) => {
        showAnalysisBanner(data.machine_id, 'error');
        markMachineAnalyzing(data.machine_id, false);
        showToast(`Analysis failed for ${data.machine_id}: ${data.error}`, 'danger');
    });
    
    socket.on('alert_generated', (data) => {
        showToast(`New Alert: ${data.title}`, 'warning');
        loadDashboardData();
        updateAlertCount();
    });
}

function updateConnectionStatus(connected) {
    const indicator = document.getElementById('connection-indicator');
    const text = document.getElementById('connection-text');
    
    if (indicator) {
        indicator.className = `status-dot ${connected ? 'bg-success' : 'bg-danger'}`;
    }
    if (text) {
        text.textContent = connected ? 'Connected' : 'Disconnected';
    }
}

// Load Dashboard Data
async function loadDashboardData() {
    try {
        const response = await fetch(`${API_BASE}/dashboard/data`);
        const data = await response.json();
        
        if (data.error) {
            console.error('Dashboard error:', data.error);
            return;
        }
        
        if (data.machines) renderMachines(data.machines);
        if (data.kpis) renderKPIs(data.kpis);
        if (data.alerts) renderAlertFeed(data.alerts);
        
        // Update last updated time
        const timestampEl = document.getElementById('last-updated');
        if (timestampEl) {
            timestampEl.textContent = new Date().toLocaleTimeString();
        }
        
        // Update alert count in sidebar
        updateAlertCount(data.kpis?.pending_alerts || 0);
        
    } catch (error) {
        console.error('Error loading dashboard:', error);
    }
}

// Render Machines Grid
function renderMachines(machines) {
    const container = document.getElementById('machines-grid');
    if (!container) return;
    
    container.innerHTML = machines.map(machine => {
        const statusClass = `status-${machine.status}`;
        const readings = machine.readings || {};
        
        // Get key readings based on machine type
        let keyReadings = '';
        if (machine.machine_type === 'MRI') {
            keyReadings = `
                <div class="machine-stat">
                    <div class="machine-stat-value">${readings.Helium_Level?.toFixed(1) || '--'}%</div>
                    <div class="machine-stat-label">Helium</div>
                </div>
                <div class="machine-stat">
                    <div class="machine-stat-value">${readings.Magnet_Temp_K?.toFixed(2) || '--'}K</div>
                    <div class="machine-stat-label">Magnet</div>
                </div>
            `;
        } else {
            keyReadings = `
                <div class="machine-stat">
                    <div class="machine-stat-value">${readings.X_ray_Tube_Temp?.toFixed(1) || '--'}°C</div>
                    <div class="machine-stat-label">Tube Temp</div>
                </div>
                <div class="machine-stat">
                    <div class="machine-stat-value">${readings.Cooling_Oil_Temp?.toFixed(1) || '--'}°C</div>
                    <div class="machine-stat-label">Oil Temp</div>
                </div>
            `;
        }
        
        return `
            <div class="col-lg-4 col-md-6 mb-4">
                <div class="machine-card" id="card-${machine.machine_id}">
                    <div class="machine-card-header ${statusClass}">
                        <div>
                            <h5 class="mb-0">${machine.machine_id}</h5>
                            <small>${machine.machine_type} - ${machine.scan_category?.toUpperCase() || ''}</small>
                        </div>
                        <div class="text-end">
                            <span class="badge bg-light text-dark">${machine.status_display?.emoji || '🟢'} ${machine.status_display?.label || 'Normal'}</span>
                        </div>
                    </div>
                    <div class="machine-card-body">
                        <div class="machine-info">
                            <div class="machine-stat">
                                <div class="machine-stat-value">${readings.Component_Temp?.toFixed(1) || '--'}°C</div>
                                <div class="machine-stat-label">Comp Temp</div>
                            </div>
                            <div class="machine-stat">
                                <div class="machine-stat-value">${readings.Vibration_Level?.toFixed(2) || '--'}</div>
                                <div class="machine-stat-label">Vibration</div>
                            </div>
                            ${keyReadings}
                        </div>
                        
                        <div class="progress mb-2" style="height: 8px;">
                            <div class="progress-bar ${getHealthBarClass(machine.health_score)}" style="width: ${machine.health_score}%"></div>
                        </div>
                        <small class="text-muted">Health Score: ${machine.health_score}%</small>
                        
                        <div class="mode-badges">
                            <span class="mode-badge operation-${machine.operation_mode}">
                                ${machine.operation_display?.icon || '✓'} ${machine.operation_display?.label || 'Normal'}
                            </span>
                            <span class="mode-badge energy-${machine.energy_mode}">
                                ${machine.energy_display?.icon || '⚡'} ${machine.energy_display?.label || 'Ready'}
                            </span>
                        </div>
                        
                        ${machine.is_analyzing ? `
                            <div class="analyzing-indicator mt-3">
                                <div class="spinner-border spinner-border-sm"></div>
                                <span>Analyzing...</span>
                            </div>
                        ` : ''}
                    </div>
                    <div class="machine-card-footer">
                        <a href="/machine/${machine.machine_id}" class="btn btn-sm btn-outline-primary flex-grow-1">
                            <i class="bi bi-eye"></i> Details
                        </a>
                        <button class="btn btn-sm btn-primary flex-grow-1" onclick="runDiagnostics('${machine.machine_id}')">
                            <i class="bi bi-activity"></i> Diagnose
                        </button>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

function getHealthBarClass(score) {
    if (score >= 80) return 'bg-success';
    if (score >= 50) return 'bg-warning';
    return 'bg-danger';
}

// Render KPIs
function renderKPIs(kpis) {
    document.getElementById('kpi-machines').textContent = kpis.total_machines || 5;
    document.getElementById('kpi-uptime').textContent = `${kpis.avg_uptime || 98}%`;
    document.getElementById('kpi-alerts').textContent = kpis.pending_alerts || 0;
    document.getElementById('kpi-critical').textContent = kpis.critical_alerts || 0;
    document.getElementById('kpi-energy').textContent = `${kpis.energy_saved_kwh || 0} kWh`;
    document.getElementById('kpi-savings').textContent = `$${(kpis.savings || 0).toLocaleString()}`;
}

// Render Alert Feed
function renderAlertFeed(alerts) {
    const container = document.getElementById('alert-feed');
    if (!container) return;
    
    if (!alerts || alerts.length === 0) {
        container.innerHTML = '<div class="text-center py-4 text-muted">No recent alerts</div>';
        return;
    }
    
    container.innerHTML = alerts.slice(0, 5).map(alert => `
        <div class="alert-item">
            <div class="d-flex justify-content-between align-items-start">
                <div>
                    <span class="alert-severity ${alert.severity}"></span>
                    <strong>${alert.machine_id}</strong>
                </div>
                <small class="text-muted">${formatTime(alert.timestamp)}</small>
            </div>
            <p class="mb-0 mt-1 small">${alert.title}</p>
            ${!alert.is_resolved ? `
                <div class="mt-2">
                    <button class="btn btn-xs btn-outline-success" onclick="resolveAlert(${alert.id})">
                        <i class="bi bi-check"></i> Resolve
                    </button>
                </div>
            ` : '<span class="badge bg-success mt-2">Resolved</span>'}
        </div>
    `).join('');
}

// Initialize Chart
function initChart() {
    const ctx = document.getElementById('telemetryChart');
    if (!ctx) return;
    
    telemetryChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Component Temp (°C)',
                    data: [],
                    borderColor: '#0d6efd',
                    tension: 0.4,
                    fill: false
                },
                {
                    label: 'Vibration (mm/s)',
                    data: [],
                    borderColor: '#ffc107',
                    tension: 0.4,
                    fill: false
                },
                {
                    label: 'Cooling (%)',
                    data: [],
                    borderColor: '#28a745',
                    tension: 0.4,
                    fill: false
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: {
                duration: 0
            },
            scales: {
                x: {
                    display: true,
                    title: {
                        display: true,
                        text: 'Time'
                    }
                },
                y: {
                    display: true,
                    title: {
                        display: true,
                        text: 'Value'
                    }
                }
            },
            plugins: {
                legend: {
                    position: 'top'
                }
            }
        }
    });
    
    // Load initial data
    loadMachineTelemetry(currentChartMachine);
}

async function loadMachineTelemetry(machineId) {
    try {
        const res = await fetch(`${API_BASE}/machine/${machineId}/telemetry`);
        const data = await res.json();
        
        if (data.history && telemetryChart) {
            const labels = data.history.map((_, i) => i);
            const temps = data.history.map(r => r.Component_Temp || 0);
            const vibrations = data.history.map(r => r.Vibration_Level || 0);
            const coolings = data.history.map(r => r.Cooling_System_Performance || 0);
            
            telemetryChart.data.labels = labels;
            telemetryChart.data.datasets[0].data = temps;
            telemetryChart.data.datasets[1].data = vibrations;
            telemetryChart.data.datasets[2].data = coolings;
            telemetryChart.update();
        }
    } catch (err) {
        console.error('Error loading telemetry:', err);
    }
}

function updateChartData(readings) {
    if (!telemetryChart) return;
    
    const maxPoints = 50;
    
    telemetryChart.data.labels.push(telemetryChart.data.labels.length);
    telemetryChart.data.datasets[0].data.push(readings.Component_Temp || 0);
    telemetryChart.data.datasets[1].data.push(readings.Vibration_Level || 0);
    telemetryChart.data.datasets[2].data.push(readings.Cooling_System_Performance || 0);
    
    if (telemetryChart.data.labels.length > maxPoints) {
        telemetryChart.data.labels.shift();
        telemetryChart.data.datasets.forEach(ds => ds.data.shift());
    }
    
    telemetryChart.update('none');
}

// Actions
async function runDiagnostics(machineId) {
    showToast(`Starting diagnostics for ${machineId}...`, 'info');
    
    try {
        const res = await fetch(`${API_BASE}/machine/${machineId}/analyze`, {
            method: 'POST'
        });
        const data = await res.json();
        
        if (data.status === 'started') {
            showToast(`Diagnostics started for ${machineId}`, 'success');
        } else if (data.status === 'already_running') {
            showToast(`Analysis already in progress for ${machineId}`, 'warning');
        }
    } catch (err) {
        console.error('Error:', err);
        showToast('Failed to start diagnostics', 'danger');
    }
}

async function analyzeAllMachines() {
    showToast('Starting analysis for all machines...', 'info');
    
    for (const machineId of MACHINE_IDS) {
        try {
            await fetch(`${API_BASE}/machine/${machineId}/analyze`, {
                method: 'POST'
            });
        } catch (err) {
            console.error(`Error analyzing ${machineId}:`, err);
        }
    }
}

async function resolveAlert(alertId) {
    try {
        const res = await fetch(`${API_BASE}/alerts/${alertId}/resolve`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({notes: 'Resolved from dashboard'})
        });
        
        const data = await res.json();
        
        if (data.success) {
            showToast('Alert resolved', 'success');
            loadDashboardData();
        }
    } catch (err) {
        console.error('Error:', err);
        showToast('Failed to resolve alert', 'danger');
    }
}

// UI Helpers
function showAnalysisBanner(machineId, status) {
    const banner = document.getElementById('analysis-banner');
    const message = document.getElementById('analysis-message');
    
    if (!banner || !message) return;
    
    if (status === 'started') {
        message.textContent = `Running diagnostics on ${machineId}...`;
        banner.classList.remove('d-none', 'alert-success', 'alert-danger');
        banner.classList.add('alert-info');
    } else if (status === 'complete') {
        message.innerHTML = `<i class="bi bi-check-circle"></i> Analysis complete for ${machineId}`;
        banner.classList.remove('alert-info', 'alert-danger');
        banner.classList.add('alert-success');
        setTimeout(() => banner.classList.add('d-none'), 3000);
    } else if (status === 'error') {
        message.innerHTML = `<i class="bi bi-x-circle"></i> Analysis failed for ${machineId}`;
        banner.classList.remove('alert-info', 'alert-success');
        banner.classList.add('alert-danger');
        setTimeout(() => banner.classList.add('d-none'), 5000);
    }
}

function markMachineAnalyzing(machineId, isAnalyzing) {
    const card = document.getElementById(`card-${machineId}`);
    if (!card) return;
    
    const indicator = card.querySelector('.analyzing-indicator');
    if (isAnalyzing && !indicator) {
        const body = card.querySelector('.machine-card-body');
        if (body) {
            body.insertAdjacentHTML('beforeend', `
                <div class="analyzing-indicator mt-3">
                    <div class="spinner-border spinner-border-sm"></div>
                    <span>Analyzing...</span>
                </div>
            `);
        }
    } else if (!isAnalyzing && indicator) {
        indicator.remove();
    }
}

function updateMachineCard(machineId, readings) {
    // Update specific values without full re-render
    const card = document.getElementById(`card-${machineId}`);
    if (!card) return;
    
    // You could update individual stat values here for smoother updates
}

function updateAlertCount(count) {
    const badge = document.getElementById('alert-count');
    if (badge) {
        badge.textContent = count || 0;
        badge.style.display = count > 0 ? 'inline-block' : 'none';
    }
}

function formatTime(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = (now - date) / 1000;
    
    if (diff < 60) return 'Just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return date.toLocaleDateString();
}

function showToast(message, type = 'info') {
    // Create toast container if not exists
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    
    const toast = document.createElement('div');
    toast.className = `alert alert-${type} alert-dismissible fade show`;
    toast.innerHTML = `
        ${message}
        <button type="button" class="btn-close" onclick="this.parentElement.remove()"></button>
    `;
    
    container.appendChild(toast);
    
    setTimeout(() => toast.remove(), 5000);
}
// Add these functions to dashboard.js

// Contact vendor
async function contactVendor(machineId) {
    const reason = prompt('Enter issue description for vendor:');
    if (!reason) return;
    
    try {
        const res = await fetch('/api/vendor/contact', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                machine_id: machineId,
                fault_summary: reason,
                urgency: 'scheduled'
            })
        });
        
        const data = await res.json();
        
        if (data.success) {
            showToast('Vendor contacted successfully', 'success');
            loadDashboardData();
        } else {
            showToast('Failed to contact vendor: ' + (data.error || 'Unknown error'), 'danger');
        }
    } catch (err) {
        console.error('Error:', err);
        showToast('Failed to contact vendor', 'danger');
    }
}

// Acknowledge alert
async function acknowledgeAlert(alertId) {
    try {
        const res = await fetch(`/api/alerts/${alertId}/acknowledge`, {
            method: 'POST'
        });
        
        const data = await res.json();
        
        if (data.success) {
            showToast('Alert acknowledged', 'success');
            loadDashboardData();
        }
    } catch (err) {
        console.error('Error:', err);
        showToast('Failed to acknowledge alert', 'danger');
    }
}

// View machine details
function viewMachineDetails(machineId) {
    window.location.href = `/machine/${machineId}`;
}

// Set machine mode
async function setMachineMode(machineId, modeType, modeValue) {
    try {
        const res = await fetch(`/api/machine/${machineId}/set-mode`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                mode_type: modeType,
                mode_value: modeValue
            })
        });
        
        const data = await res.json();
        
        if (data.success) {
            showToast(`${modeType} mode set to ${modeValue}`, 'success');
            loadDashboardData();
        }
    } catch (err) {
        console.error('Error:', err);
        showToast('Failed to set mode', 'danger');
    }
}

// Reset machine maintenance
async function resetMaintenance(machineId) {
    if (!confirm('Mark maintenance as complete? This will reset alerts and degradation.')) return;
    
    try {
        const res = await fetch(`/api/machine/${machineId}/reset-maintenance`, {
            method: 'POST'
        });
        
        const data = await res.json();
        
        if (data.success) {
            showToast('Maintenance completed successfully', 'success');
            loadDashboardData();
        }
    } catch (err) {
        console.error('Error:', err);
        showToast('Failed to reset maintenance', 'danger');
    }
}

// Export functions
window.contactVendor = contactVendor;
window.acknowledgeAlert = acknowledgeAlert;
window.viewMachineDetails = viewMachineDetails;
window.setMachineMode = setMachineMode;
window.resetMaintenance = resetMaintenance;

// Export functions for use in templates
window.runDiagnostics = runDiagnostics;
window.analyzeAllMachines = analyzeAllMachines;
window.resolveAlert = resolveAlert;
window.initDashboard = initDashboard;