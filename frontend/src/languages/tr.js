const tr = {
  // Login
  login: {
    title: "Giriş Yap",
    username: "Kullanıcı Adı",
    password: "Şifre",
    submit: "Giriş Yap",
    loading: "Giriş yapılıyor...",
    error: "Kullanıcı adı veya şifre hatalı.",
  },

  // Topbar
  topbar: {
    logout: "Çıkış",
  },

  // Patient List
  patientList: {
    title: "Hasta Paneli",
    search: "🔍  Hasta ara...",
    addPatient: "+ Hasta Ekle",
    newPatient: "Yeni Hasta",
    fullName: "Ad Soyad",
    gestationalAge: "Gestasyonel Yaş (hafta)",
    postnatalAge: "Postnatal Yaş (gün)",
    save: "Kaydet",
    cancel: "İptal",
    id: "ID",
    name: "Ad",
    ageDays: "Yaş (gün)",
    status: "Durum",
    lastUpdated: "Son Güncelleme",
    actions: "İşlemler",
    view: "Görüntüle",
    noPatients: "Hasta bulunamadı.",
    stable: "Stabil",
    critical: "Kritik",
    monitoring: "İzleniyor",
    inactive: "Pasif",
    loading: "Hastalar yükleniyor...",
    errorAdd: "Hasta eklenemedi.",
  },

  // Patient Detail
  patientDetail: {
    patientInfo: "Hasta Bilgisi",
    deviceConnected: "Cihaz Bağlı",
    monitoringActive: "Gerçek zamanlı izleme aktif",
    noCriticalAlerts: "✓ Kritik Alert Yok",
    activeAlerts: "aktif alert",
    criticalAlert: "⚠ KRİTİK ALERT",
    loading: "Yükleniyor...",
  },

  // Tabs
  tabs: {
    realTimeMonitor: "Gerçek Zamanlı İzleme",
    aiResults: "AI Sonuçları",
    trendAnalysis: "Trend Analizi",
    reports: "Raporlar",
  },

  // Real Time Monitor
  monitor: {
    heartRate: "Kalp Atışı",
    spo2: "SpO₂",
    respRate: "Solunum Hızı",
    ecgWaveform: "ECG Dalgaformu",
    ecgPlaceholder: "Canlı ECG izleme ekranı (dalga formu görselleştirmesi)",
    wsConnected: "WebSocket bağlı",
    wsConnecting: "Bağlanıyor...",
    wsDisconnected: "Bağlantı kesildi",
    activeAlerts: "Aktif Alertler",
    acknowledge: "Onayla",
    resolve: "Çöz",
  },

  // AI Results
  ai: {
    title: "AI Risk Değerlendirmesi",
    timestamp: "Analiz Zamanı",
    refresh: "↻ Yenile",
    riskScore: "Risk Skoru",
    scale: "(Ölçek: 0-1)",
    model: "Model",
    highRisk: "YÜKSEK RİSK",
    mediumRisk: "ORTA RİSK",
    lowRisk: "DÜŞÜK RİSK",
    clinical: "Klinik Yorum",
    topFeatures: "En Etkili Özellikler",
    noResults: "Henüz AI sonucu yok.",
    loading: "AI sonuçları yükleniyor...",
    disclaimer: "Not: Bu AI değerlendirmesi klinik kararı desteklemek amacıyla sunulmaktadır, yerini almaz.",
    highDesc: "AI modeli hastanın vital bulgularında endişe verici bir patern tespit etti. Acil klinik değerlendirme önerilir.",
    mediumDesc: "AI modeli bazı anormal paternler tespit etti. Yakın izlem önerilir.",
    lowDesc: "Vital bulgular kabul edilebilir sınırlar içinde. Rutin izleme devam etsin.",
  },

  // Trend Analysis
  trend: {
    timeRange: "Zaman Aralığı",
    last6h: "Son 6 Saat",
    last24h: "Son 24 Saat",
    last7d: "Son 7 Gün",
    heartRateTrend: "Kalp Atışı Trendi",
    spo2Trend: "SpO₂ Trendi",
    noData: "Veri yok",
    summary: "Özet İstatistikler",
    avg: "Ort",
    min: "Min",
    max: "Maks",
    loading: "Trend verisi yükleniyor...",
  },

  // Reports
  reports: {
    config: "Rapor Yapılandırması",
    preview: "Rapor Önizleme",
    dateRange: "Tarih Aralığı",
    from: "Başlangıç:",
    to: "Bitiş:",
    period: "Dönem",
    last1d: "Son 1 gün",
    last3d: "Son 3 gün",
    last7d: "Son 7 gün",
    last14d: "Son 14 gün",
    last30d: "Son 30 gün",
    include: "Rapora Dahil Et",
    items: [
      "Hasta demografik bilgileri",
      "Vital bulgu özeti ve trendleri",
      "Kritik alertler ve olay kaydı",
      "AI değerlendirme sonuçları",
    ],
    generate: "PDF Rapor Oluştur",
    generating: "Oluşturuluyor...",
    noPermission: "Rapor oluşturma Doctor rolü gerektirir.",
    error: "Rapor oluşturulamadı.",
    confirmTitle: "Rapor Oluşturulsun mu?",
    confirmMsg: "seçili dönem için PDF rapor oluşturulacak ve indirilecek.",
    confirmYes: "Evet, Oluştur",
    confirmNo: "İptal",
    previewTitle: "NICU Klinik Raporu",
    previewContent: "[Rapor içeriği önizlemesi]",
    vitalSummary: "Vital Bulgu Özeti",
    aiResults: "AI Değerlendirme Sonuçları",
    alertHistory: "Alert Geçmişi",
  },

  // Admin
  admin: {
    title: "Yönetim Paneli",
    userManagement: "Kullanıcı Yönetimi",
    systemSettings: "Sistem Ayarları",
    auditLogs: "Denetim Kayıtları",
    dbBackup: "Veritabanı Yedekleme",
    addUser: "+ Kullanıcı Ekle",
    newUser: "Yeni Kullanıcı",
    username: "Kullanıcı Adı",
    password: "Şifre",
    displayName: "Görünen Ad",
    role: "Rol",
    save: "Kaydet",
    cancel: "İptal",
    usernameCol: "Kullanıcı Adı",
    fullName: "Ad Soyad",
    roleCol: "Rol",
    status: "Durum",
    actions: "İşlemler",
    active: "Aktif",
    inactive: "Pasif",
    deactivate: "Deaktif Et",
    activate: "Aktif Et",
    loading: "Kullanıcılar yükleniyor...",
    errorAdd: "Kullanıcı eklenemedi.",
    rolesTitle: "Rol Yetkileri",
    roles: {
      ADMINISTRATOR: "Tam sistem erişimi, kullanıcı yönetimi, yapılandırma",
      DOCTOR: "Hasta verisi görüntüleme/düzenleme, rapor oluşturma, AI sonuçlarına erişim",
      NURSE: "Hasta izleme, alert onaylama, vital bulgu güncelleme",
    },
  },

  // Common
  common: {
    ga: "GY",
    pna: "PNA",
    weeks: "hafta",
    days: "gün",
  },
};

export default tr;