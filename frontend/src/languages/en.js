const en = {
  // Login
  login: {
    title: "Login",
    username: "Username",
    password: "Password",
    submit: "Login",
    loading: "Logging in...",
    error: "Invalid username or password.",
  },

  // Topbar
  topbar: {
    logout: "Logout",
  },

  // Patient List
  patientList: {
    title: "Patient Dashboard",
    search: "🔍  Search patients...",
    addPatient: "+ Add Patient",
    newPatient: "New Patient",
    fullName: "Full Name",
    gestationalAge: "Gestational Age (weeks)",
    postnatalAge: "Postnatal Age (days)",
    save: "Save",
    cancel: "Cancel",
    id: "ID",
    name: "Name",
    ageDays: "Age (days)",
    status: "Status",
    lastUpdated: "Last Updated",
    actions: "Actions",
    view: "View",
    noPatients: "No patients found.",
    stable: "Stable",
    critical: "Critical",
    monitoring: "Monitoring",
    inactive: "Inactive",
    loading: "Loading patients...",
    errorAdd: "Failed to add patient.",
  },

  // Patient Detail
  patientDetail: {
    patientInfo: "Patient Info",
    deviceConnected: "Device Connected",
    monitoringActive: "Real-time monitoring active",
    noCriticalAlerts: "✓ No Critical Alerts",
    activeAlerts: "active alert(s)",
    criticalAlert: "⚠ CRITICAL ALERT",
    loading: "Loading...",
  },

  // Tabs
  tabs: {
    realTimeMonitor: "Real-Time Monitor",
    aiResults: "AI Results",
    trendAnalysis: "Trend Analysis",
    reports: "Reports",
  },

  // Real Time Monitor
  monitor: {
    heartRate: "Heart Rate",
    spo2: "SpO₂",
    respRate: "Resp. Rate",
    ecgWaveform: "ECG Waveform",
    ecgPlaceholder: "Live ECG monitoring display (waveform visualization)",
    wsConnected: "WebSocket connected",
    wsConnecting: "Connecting...",
    wsDisconnected: "Disconnected",
    activeAlerts: "Active Alerts",
    acknowledge: "Acknowledge",
    resolve: "Resolve",
  },

  // AI Results
  ai: {
    title: "AI Risk Assessment",
    timestamp: "Analysis Timestamp",
    refresh: "↻ Refresh",
    riskScore: "Risk Score",
    scale: "(Scale: 0-1)",
    model: "Model",
    highRisk: "HIGH RISK",
    mediumRisk: "MEDIUM RISK",
    lowRisk: "LOW RISK",
    clinical: "Clinical Interpretation",
    topFeatures: "Top Contributing Features",
    noResults: "No AI results yet.",
    loading: "Loading AI results...",
    disclaimer: "Note: This AI-generated assessment is intended to support, not replace, clinical judgment.",
    highDesc: "The AI model has identified a concerning pattern in the patient's vital signs. Immediate clinical assessment is recommended.",
    mediumDesc: "The AI model has detected some abnormal patterns. Close monitoring is advised.",
    lowDesc: "Vital signs are within acceptable ranges. Continue routine monitoring.",
  },

  // Trend Analysis
  trend: {
    timeRange: "Time Range:",
    last6h: "Last 6 Hours",
    last24h: "Last 24 Hours",
    last7d: "Last 7 Days",
    heartRateTrend: "Heart Rate Trend",
    spo2Trend: "SpO₂ Trend",
    noData: "No data available",
    summary: "Summary Statistics",
    avg: "Avg",
    min: "Min",
    max: "Max",
    loading: "Loading trend data...",
  },

  // Reports
  reports: {
    config: "Report Configuration",
    preview: "Report Preview",
    dateRange: "Date Range",
    from: "From:",
    to: "To:",
    period: "Period",
    last1d: "Last 1 day",
    last3d: "Last 3 days",
    last7d: "Last 7 days",
    last14d: "Last 14 days",
    last30d: "Last 30 days",
    include: "Include in Report",
    items: [
      "Patient demographic information",
      "Vital signs summary and trends",
      "Critical alerts and events log",
      "AI assessment results",
    ],
    generate: "Generate PDF Report",
    generating: "Generating...",
    noPermission: "Report generation requires Doctor role.",
    error: "Report generation failed.",
    confirmTitle: "Generate Report?",
    confirmMsg: "A PDF report will be generated and downloaded for the selected period.",
    confirmYes: "Yes, Generate",
    confirmNo: "Cancel",
    previewTitle: "NICU Clinical Report",
    previewContent: "[Report content preview]",
    vitalSummary: "Vital Signs Summary",
    aiResults: "AI Assessment Results",
    alertHistory: "Alert History",
  },

  // Admin
  admin: {
    title: "Administration Panel",
    userManagement: "User Management",
    systemSettings: "System Settings",
    auditLogs: "Audit Logs",
    dbBackup: "Database Backup",
    addUser: "+ Add User",
    newUser: "New User",
    username: "Username",
    password: "Password",
    displayName: "Display Name",
    role: "Role",
    save: "Save",
    cancel: "Cancel",
    usernameCol: "Username",
    fullName: "Full Name",
    roleCol: "Role",
    status: "Status",
    actions: "Actions",
    active: "Active",
    inactive: "Inactive",
    deactivate: "Deactivate",
    activate: "Activate",
    loading: "Loading users...",
    errorAdd: "Failed to add user.",
    rolesTitle: "Role Permissions Overview",
    roles: {
      ADMINISTRATOR: "Full system access, user management, configuration",
      DOCTOR: "View/edit patient data, generate reports, access AI results",
      NURSE: "Monitor patients, acknowledge alerts, update vital signs",
    },
  },

  // Common
  common: {
    ga: "GA",
    pna: "PNA",
    weeks: "w",
    days: "d",
  },
};

export default en;