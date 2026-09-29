import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

const resources = {
  en: {
    translation: {
      nav: {
        home: 'Home',
        citizenArea: 'Citizen Area',
        nationalMap: 'National Map',
        incidents: 'Incidents',
        dashboard: 'Dashboard',
        liveMap: 'Live Map',
        reportWeather: 'Report Weather Event',
        trackReport: 'Track Report',
        analytics: 'Analytics',
        verificationQueue: 'Verification Queue',
        login: 'Operator Access',
        logout: 'Logout',
      },
      citizen: {
        title: 'My Area Citizen Dashboard',
        subtitle: 'Hyper-local weather risk overview & emergency route blockage check around your location',
        activeHazards: 'Active Hazards Nearby',
        nearestHazard: 'Nearest Incident',
        peakSeverity: 'Peak Severity',
        areaSafetyStatus: 'Public Safety Status',
        pathClear: 'Path Clear',
        pathAffected: 'Path Affected',
        reliefCenters: 'Nearby Relief Centers & Evacuation Shelters',
        emergencyContacts: 'Emergency Helplines & SOS Quick Dial',
      },
    },
  },
  hi: {
    translation: {
      nav: {
        home: 'मुख्य पृष्ठ',
        citizenArea: 'नागरिक क्षेत्र',
        nationalMap: 'राष्ट्रीय मानचित्र',
        incidents: 'आपदा घटनाएं',
        dashboard: 'डैशबोर्ड',
        liveMap: 'लाइव मैप',
        reportWeather: 'घटना की रिपोर्ट करें',
        trackReport: 'रिपोर्ट ट्रैक करें',
        analytics: 'विश्लेषण',
        verificationQueue: 'सत्यापन कतार',
        login: 'ऑपरेटर पहुंच',
        logout: 'लॉगआउट',
      },
      citizen: {
        title: 'मेरा क्षेत्र नागरिक डैशबोर्ड',
        subtitle: 'आपके स्थान के आसपास हाइपर-लोकल मौसम जोखिम अवलोकन और मार्ग अवरोध जांच',
        activeHazards: 'आसपास सक्रिय खतरे',
        nearestHazard: 'निकटतम घटना',
        peakSeverity: 'सर्वोच्च गंभीरता',
        areaSafetyStatus: 'जन सुरक्षा स्थिति',
        pathClear: 'मार्ग सुरक्षित है',
        pathAffected: 'मार्ग प्रभावित है',
        reliefCenters: 'आसपास के राहत शिविर और अस्पताल',
        emergencyContacts: 'आपत्कालीन हेल्पलाइन नंबर',
      },
    },
  },
};

i18n.use(initReactI18next).init({
  resources,
  lng: localStorage.getItem('nwbda_lang') || 'en',
  fallbackLng: 'en',
  interpolation: {
    escapeValue: false,
  },
});

export default i18n;
