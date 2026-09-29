import React, { useState, useRef, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  Cloud,
  Bell,
  Menu,
  X,
  User,
  LogOut,
  Globe,
  ShieldCheck,
  ChevronDown,
  LayoutDashboard,
  FileText,
  SearchCheck,
  CheckSquare,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { CitySearchBar } from '@/components/common/CitySearchBar';
import { useAuth } from '@/context/AuthContext';

export const Navbar: React.FC = () => {
  const location = useLocation();
  const { i18n, t } = useTranslation();
  const { isAuthenticated, user, isOperator, isCitizen, isAdmin, logout } = useAuth();

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [toolsDropdownOpen, setToolsDropdownOpen] = useState(false);
  const toolsRef = useRef<HTMLDivElement>(null);

  const currentLang = i18n.language || 'en';

  const toggleLanguage = () => {
    const nextLang = currentLang === 'en' ? 'hi' : 'en';
    i18n.changeLanguage(nextLang);
    localStorage.setItem('nwbda_lang', nextLang);
  };

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (toolsRef.current && !toolsRef.current.contains(e.target as Node)) {
        setToolsDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Primary navigation links tailored by role and auth state
  const primaryLinks = [
    ...(!isAuthenticated
      ? [{ name: t('nav.home', 'Home'), path: '/welcome' }]
      : []),
    ...(isCitizen || !isAuthenticated
      ? [
          {
            name: t('nav.citizenArea', 'Citizen Area'),
            path: '/citizen-dashboard',
          },
        ]
      : []),
    { name: t('nav.nationalMap', 'National Map'), path: '/national-map' },
    { name: t('nav.liveMap', 'Live Map'), path: '/live-map' },
    { name: t('nav.incidents', 'Incidents'), path: '/incidents' },
    { name: t('nav.analytics', 'Analytics'), path: '/analytics' },
  ];

  // Secondary tools dropdown items tailored by role
  const toolItems = isCitizen
    ? [
        {
          name: t('nav.reportWeather', 'Report Weather Event'),
          path: '/report',
          icon: FileText,
          desc: 'Submit citizen eyewitness observations',
        },
        {
          name: t('nav.trackReport', 'Track Incident Report'),
          path: '/track-report',
          icon: SearchCheck,
          desc: 'Query report status by tracking ID',
        },
      ]
    : [
        {
          name: t('nav.dashboard', 'Operations Dashboard'),
          path: '/dashboard',
          icon: LayoutDashboard,
          desc: 'Real-time telemetry and regional KPIs',
        },
        ...(isAdmin
          ? [
              {
                name: t('nav.trackReport', 'Track Incident Report'),
                path: '/track-report',
                icon: SearchCheck,
                desc: 'Query report status by tracking ID',
              },
            ]
          : []),
      ];

  if (isCitizen) {
    toolItems.push({
      name: 'My Submitted Reports',
      path: '/my-reports',
      icon: FileText,
      desc: 'View status and review updates on your reports',
    });
  }

  if (isOperator) {
    toolItems.push({
      name: t('nav.verificationQueue', 'Operator Triage Queue'),
      path: '/admin/queue',
      icon: CheckSquare,
      desc: 'Authorized operator verification and triage',
    });
  }

  const isToolActive = toolItems.some((item) => location.pathname === item.path);

  return (
    <header className="sticky top-0 z-50 w-full border-b border-slate-200 bg-white/95 backdrop-blur-md shadow-2xs">
      <div className="w-full max-w-[1720px] mx-auto flex h-16 items-center justify-between px-3 sm:px-4 lg:px-6 gap-2">
        {/* Left: Mobile Hamburger & Brand Logo */}
        <div className="flex items-center space-x-2.5 shrink-0">
          <button
            type="button"
            className="rounded-lg p-1.5 text-slate-700 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-600 lg:hidden cursor-pointer"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-label="Toggle navigation menu"
            aria-expanded={mobileMenuOpen}
          >
            {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>

          <Link to="/" className="flex items-center space-x-2 shrink-0">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-white shadow-xs">
              <Cloud className="h-4.5 w-4.5" />
            </div>
            <div className="flex flex-col">
              <span className="font-black tracking-tight text-blue-900 text-sm whitespace-nowrap">
                NWBDA <span className="hidden xl:inline font-bold text-slate-500 text-xs">Platform</span>
              </span>
            </div>
          </Link>
        </div>

        {/* Center: Desktop Navigation Links + Tools Dropdown */}
        <nav className="hidden lg:flex lg:h-full lg:items-center lg:space-x-0.5 xl:space-x-1">
          {primaryLinks.map((link) => {
            const isActive = location.pathname === link.path;
            return (
              <Link
                key={link.path}
                to={link.path}
                className={`relative flex h-full items-center px-1.5 2xl:px-2.5 py-1 text-xs 2xl:text-sm font-semibold whitespace-nowrap transition-colors ${
                  isActive
                    ? 'text-blue-600 after:absolute after:bottom-0 after:left-0 after:h-0.5 after:w-full after:bg-blue-600'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50/80 rounded-md'
                }`}
              >
                {link.name}
              </Link>
            );
          })}

          {/* Tools / Modules Dropdown */}
          <div ref={toolsRef} className="relative h-full flex items-center">
            <button
              type="button"
              onClick={() => setToolsDropdownOpen(!toolsDropdownOpen)}
              className={`relative flex h-full items-center space-x-1 px-1.5 2xl:px-2.5 py-1 text-xs 2xl:text-sm font-semibold whitespace-nowrap transition-colors cursor-pointer ${
                isToolActive
                  ? 'text-blue-600 after:absolute after:bottom-0 after:left-0 after:h-0.5 after:w-full after:bg-blue-600'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50/80 rounded-md'
              }`}
            >
              <span>{t('nav.tools', 'Services & Tools')}</span>
              <ChevronDown className={`h-3 w-3 transition-transform ${toolsDropdownOpen ? 'rotate-180' : ''}`} />
            </button>

            {toolsDropdownOpen && (
              <div className="absolute left-0 top-[calc(100%-4px)] z-50 w-72 rounded-2xl border border-slate-200 bg-white p-2 shadow-xl animate-in fade-in slide-in-from-top-1 duration-150 space-y-1">
                <div className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  Platform Services
                </div>
                {toolItems.map((item) => {
                  const Icon = item.icon;
                  const isActive = location.pathname === item.path;
                  return (
                    <Link
                      key={item.path}
                      to={item.path}
                      onClick={() => setToolsDropdownOpen(false)}
                      className={`flex items-start space-x-3 rounded-xl p-2.5 transition-colors ${
                        isActive
                          ? 'bg-blue-50 text-blue-700'
                          : 'text-slate-700 hover:bg-slate-50 hover:text-slate-900'
                      }`}
                    >
                      <div className={`mt-0.5 flex h-7 w-7 items-center justify-center rounded-lg ${
                        isActive ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600'
                      }`}>
                        <Icon className="h-4 w-4" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-bold leading-tight truncate">{item.name}</div>
                        <div className="text-[11px] text-slate-500 leading-tight truncate mt-0.5">{item.desc}</div>
                      </div>
                    </Link>
                  );
                })}
              </div>
            )}
          </div>

          {/* Quick Role Shortcuts if authenticated */}
          {isOperator && (
            <Link
              to="/admin/queue"
              className={`relative flex h-full items-center px-1.5 2xl:px-2 py-1 text-xs font-bold whitespace-nowrap transition-colors ${
                location.pathname === '/admin/queue'
                  ? 'text-blue-600 after:absolute after:bottom-0 after:left-0 after:h-0.5 after:w-full after:bg-blue-600'
                  : 'text-emerald-700 hover:text-emerald-800'
              }`}
            >
              <span className="flex items-center space-x-1 bg-emerald-50 border border-emerald-200/80 px-2 py-0.5 rounded-full">
                <ShieldCheck className="h-3 w-3 text-emerald-600" />
                <span>Triage Queue</span>
              </span>
            </Link>
          )}

          {isCitizen && (
            <Link
              to="/my-reports"
              className={`relative flex h-full items-center px-1.5 2xl:px-2 py-1 text-xs font-bold whitespace-nowrap transition-colors ${
                location.pathname === '/my-reports'
                  ? 'text-blue-600 after:absolute after:bottom-0 after:left-0 after:h-0.5 after:w-full after:bg-blue-600'
                  : 'text-emerald-700 hover:text-emerald-800'
              }`}
            >
              <span className="flex items-center space-x-1 bg-emerald-50 border border-emerald-200/80 px-2 py-0.5 rounded-full">
                <FileText className="h-3 w-3 text-emerald-600" />
                <span>My Reports</span>
              </span>
            </Link>
          )}
        </nav>

        {/* Right: Language Switcher, Compact Search & Auth Status */}
        <div className="flex items-center space-x-1.5 sm:space-x-2 shrink-0">
          {/* Language Switcher Toggle */}
          <button
            type="button"
            onClick={toggleLanguage}
            className="inline-flex items-center space-x-1 px-2 py-1 rounded-lg border border-slate-200 bg-slate-50 text-slate-700 text-xs font-bold hover:bg-slate-100 transition-colors shrink-0 cursor-pointer"
            title="Switch Language (English / हिंदी)"
          >
            <Globe className="h-3.5 w-3.5 text-blue-600" />
            <span>{currentLang === 'en' ? 'HI' : 'EN'}</span>
          </button>

          {/* Desktop City Search Bar */}
          <div className="hidden sm:block w-32 md:w-36 lg:w-40 xl:w-44">
            <CitySearchBar isCompact />
          </div>

          {isAuthenticated ? (
            <div className="flex items-center space-x-1.5 shrink-0">
              <span
                className={`hidden md:inline-flex items-center px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider border ${
                  user?.role === 'ADMIN'
                    ? 'bg-purple-50 text-purple-700 border-purple-200'
                    : user?.role === 'OPERATOR'
                    ? 'bg-blue-50 text-blue-700 border-blue-200'
                    : 'bg-emerald-50 text-emerald-700 border-emerald-200'
                }`}
              >
                {user?.role === 'ADMIN'
                  ? '🛡️ ADMIN'
                  : user?.role === 'OPERATOR'
                  ? '🛡️ OPERATOR'
                  : '👤 CITIZEN'}
              </span>
              <button
                type="button"
                onClick={logout}
                className="inline-flex items-center space-x-1 px-2 py-1 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs font-bold hover:bg-rose-100 transition-colors shrink-0 cursor-pointer"
                title="Logout Session"
              >
                <LogOut className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Logout</span>
              </button>
            </div>
          ) : (
            <div className="flex items-center space-x-1.5 shrink-0">
              <Link
                to="/login"
                className="inline-flex items-center text-xs font-bold text-slate-700 hover:text-blue-600 px-2 py-1 rounded-lg transition-colors shrink-0"
              >
                Sign In
              </Link>
              <Link
                to="/signup"
                className="hidden sm:inline-flex items-center text-xs font-bold text-white bg-emerald-600 hover:bg-emerald-700 px-2.5 py-1 rounded-lg transition-colors shrink-0 shadow-2xs"
              >
                Citizen Sign Up
              </Link>
            </div>
          )}

          <button
            type="button"
            className="rounded-full p-1.5 text-slate-600 hover:bg-slate-100 hover:text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 shrink-0 cursor-pointer"
            aria-label="View notifications"
          >
            <Bell className="h-4 w-4" />
          </button>

          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-100 border border-slate-200 text-slate-600 shadow-2xs overflow-hidden shrink-0">
            <User className="h-3.5 w-3.5 text-slate-500" />
          </div>
        </div>
      </div>

      {/* Mobile Drawer Menu & Search */}
      {mobileMenuOpen && (
        <div className="border-b border-slate-200 bg-white px-4 py-3 lg:hidden space-y-3 shadow-lg">
          {/* Mobile City Search Bar */}
          <div className="w-full">
            <CitySearchBar placeholder="Search Indian city or district..." />
          </div>

          <nav className="flex flex-col space-y-1">
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 px-3 pt-1">
              Primary Navigation
            </div>
            {primaryLinks.map((link) => {
              const isActive = location.pathname === link.path;
              return (
                <Link
                  key={link.path}
                  to={link.path}
                  onClick={() => setMobileMenuOpen(false)}
                  className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-blue-50 text-blue-700 font-bold'
                      : 'text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  {link.name}
                </Link>
              );
            })}

            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 px-3 pt-2">
              Services & Tools
            </div>
            {toolItems.map((item) => {
              const Icon = item.icon;
              const isActive = location.pathname === item.path;
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  onClick={() => setMobileMenuOpen(false)}
                  className={`flex items-center space-x-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-blue-50 text-blue-700 font-bold'
                      : 'text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  <Icon className="h-4 w-4 text-slate-500" />
                  <span>{item.name}</span>
                </Link>
              );
            })}

            <div className="border-t border-slate-100 pt-2 flex items-center justify-between">
              {isAuthenticated ? (
                <button
                  type="button"
                  onClick={() => {
                    logout();
                    setMobileMenuOpen(false);
                  }}
                  className="flex items-center space-x-1.5 text-sm font-bold text-rose-600 px-3 py-2 cursor-pointer"
                >
                  <LogOut className="h-4 w-4" />
                  <span>Logout Operator Session</span>
                </button>
              ) : (
                <Link
                  to="/login"
                  onClick={() => setMobileMenuOpen(false)}
                  className="block rounded-lg px-3 py-2 text-sm font-bold text-blue-600 hover:bg-blue-50"
                >
                  Operator Login Portal
                </Link>
              )}
            </div>
          </nav>
        </div>
      )}
    </header>
  );
};

