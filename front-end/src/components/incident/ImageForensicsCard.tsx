// Image Forensics & EXIF Consistency Card Component (S2 Item 9)

import React from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import {
  Camera,
  CheckCircle2,
  AlertTriangle,
  MinusCircle,
  ExternalLink,
  ShieldAlert,
  Clock,
  MapPin,
  Copy,
} from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { IncidentImageForensicsDetail, ImageForensicItemDetail } from '@/types/incident';

interface ImageForensicsCardProps {
  forensics?: IncidentImageForensicsDetail | null;
}

export const ImageForensicsCard: React.FC<ImageForensicsCardProps> = ({ forensics }) => {
  const { t } = useTranslation();
  const { isOperator, isAdmin } = useAuth();
  const canAccessOperatorLinks = Boolean(isOperator || isAdmin);

  if (!forensics || !forensics.images || forensics.images.length === 0) {
    return null;
  }

  const getVerdictBadge = (verdict: string) => {
    switch (verdict) {
      case 'SUPPORTS':
        return {
          icon: <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" aria-hidden="true" />,
          label: t('imageForensics.verdictSupports', 'CONSISTENT'),
          className: 'bg-emerald-50 text-emerald-700 border-emerald-200',
        };
      case 'CONTRADICTS':
        return {
          icon: <AlertTriangle className="h-3.5 w-3.5 text-rose-600" aria-hidden="true" />,
          label: t('imageForensics.verdictContradicts', 'CONTRADICTS'),
          className: 'bg-rose-50 text-rose-700 border-rose-200',
        };
      default:
        return {
          icon: <MinusCircle className="h-3.5 w-3.5 text-slate-500" aria-hidden="true" />,
          label: t('imageForensics.verdictNeutral', 'NEUTRAL'),
          className: 'bg-slate-100 text-slate-600 border-slate-200',
        };
    }
  };

  const overallStyle = getVerdictBadge(forensics.overall_verdict);

  return (
    <div
      className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6 shadow-2xs space-y-4"
      data-testid="image-forensics-card"
    >
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center space-x-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
            <Camera className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="text-sm sm:text-base font-bold text-slate-900">
                {t('imageForensics.title', 'Image Forensics & EXIF Consistency')}
              </h3>
              {forensics.is_simulated && (
                <span className="inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-200">
                  {t('imageForensics.simulatedBadge', 'SIMULATED')}
                </span>
              )}
            </div>
            <p className="text-[11px] text-slate-500">
              {t(
                'imageForensics.subtitle',
                'Cryptographic hashing, perceptual hash reuse detection, and EXIF consistency checks'
              )}
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <span
            className={`inline-flex items-center space-x-1 rounded-lg px-2.5 py-1 text-xs font-bold border ${overallStyle.className}`}
          >
            {overallStyle.icon}
            <span>{overallStyle.label}</span>
          </span>
          {forensics.total_credibility_adjustment !== 0 && (
            <span
              className={`inline-flex items-center rounded-lg px-2 py-1 text-xs font-semibold ${
                forensics.total_credibility_adjustment > 0
                  ? 'bg-emerald-50 text-emerald-700'
                  : 'bg-rose-50 text-rose-700'
              }`}
            >
              {forensics.total_credibility_adjustment > 0 ? '+' : ''}
              {forensics.total_credibility_adjustment.toFixed(2)} Credibility
            </span>
          )}
        </div>
      </div>

      {/* Forensic Items List */}
      <div className="space-y-3 pt-2 border-t border-slate-100">
        {forensics.images.map((img: ImageForensicItemDetail, idx: number) => {
          const itemStyle = getVerdictBadge(img.overall_verdict);

          return (
            <div
              key={img.id || idx}
              className="rounded-xl border border-slate-200/90 bg-slate-50/50 p-4 space-y-3 hover:border-slate-300 transition-colors"
            >
              {/* Image Item Sub-header */}
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center space-x-2">
                  <span className="text-xs font-bold text-slate-700">
                    Photo #{idx + 1}
                  </span>
                  <span className="font-mono text-[10px] text-slate-400 bg-white px-1.5 py-0.5 rounded border border-slate-200">
                    SHA: {img.sha256.substring(0, 10)}...
                  </span>
                  {img.phash && (
                    <span className="font-mono text-[10px] text-slate-400 bg-white px-1.5 py-0.5 rounded border border-slate-200">
                      pHash: {img.phash}
                    </span>
                  )}
                </div>

                <span
                  className={`inline-flex items-center space-x-1 rounded-md px-2 py-0.5 text-[11px] font-bold border ${itemStyle.className}`}
                >
                  {itemStyle.icon}
                  <span>{itemStyle.label}</span>
                </span>
              </div>

              {/* Forensic Checks Breakdown */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                {/* 1. Time Check */}
                <div className="rounded-lg bg-white p-2.5 border border-slate-200/80 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-semibold text-slate-600 flex items-center space-x-1">
                      <Clock className="h-3 w-3 text-slate-400" aria-hidden="true" />
                      <span>{t('imageForensics.timeConsistency', 'Capture Time')}</span>
                    </span>
                    <span
                      className={`text-[10px] font-bold px-1.5 py-0.2 rounded ${
                        getVerdictBadge(img.time_verdict).className
                      }`}
                    >
                      {getVerdictBadge(img.time_verdict).label}
                    </span>
                  </div>
                  <p className="text-[10px] text-slate-500 leading-relaxed">
                    {img.has_exif
                      ? img.time_difference
                        ? `${t('imageForensics.timeGap', 'Time Gap')}: ${img.time_difference}`
                        : 'Capture timestamp consistent'
                      : t('imageForensics.noExifReason', 'No EXIF metadata (neutral)')}
                  </p>
                </div>

                {/* 2. Location Check */}
                <div className="rounded-lg bg-white p-2.5 border border-slate-200/80 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-semibold text-slate-600 flex items-center space-x-1">
                      <MapPin className="h-3 w-3 text-slate-400" aria-hidden="true" />
                      <span>{t('imageForensics.locationConsistency', 'Location')}</span>
                    </span>
                    <span
                      className={`text-[10px] font-bold px-1.5 py-0.2 rounded ${
                        getVerdictBadge(img.location_verdict).className
                      }`}
                    >
                      {getVerdictBadge(img.location_verdict).label}
                    </span>
                  </div>
                  <p className="text-[10px] text-slate-500 leading-relaxed">
                    {img.location_difference
                      ? `${t('imageForensics.distance', 'Distance')}: ${img.location_difference}`
                      : t('imageForensics.noExifReason', 'No GPS metadata (neutral)')}
                  </p>
                </div>

                {/* 3. Reuse Check */}
                <div className="rounded-lg bg-white p-2.5 border border-slate-200/80 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-semibold text-slate-600 flex items-center space-x-1">
                      <Copy className="h-3 w-3 text-slate-400" aria-hidden="true" />
                      <span>{t('imageForensics.reuseDetection', 'Reuse Check')}</span>
                    </span>
                    <span
                      className={`text-[10px] font-bold px-1.5 py-0.2 rounded ${
                        getVerdictBadge(img.reuse_verdict).className
                      }`}
                    >
                      {getVerdictBadge(img.reuse_verdict).label}
                    </span>
                  </div>
                  <p className="text-[10px] text-slate-500 leading-relaxed">
                    {img.matched_incident_ids && img.matched_incident_ids.length > 0
                      ? `${t('imageForensics.reuseDetected', 'Found in other incident')}`
                      : t('imageForensics.noReuse', 'No duplicate matches')}
                  </p>
                </div>
              </div>

              {/* Operator Cross-Incident Links (P5) */}
              {img.matched_incident_ids && img.matched_incident_ids.length > 0 && (
                <div className="rounded-lg bg-rose-50 border border-rose-200 p-2.5 space-y-1.5">
                  <div className="flex items-center space-x-1.5 text-xs font-bold text-rose-800">
                    <ShieldAlert className="h-3.5 w-3.5" aria-hidden="true" />
                    <span>
                      {t('imageForensics.reusedIn', 'Reused in Incident')}:
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {img.matched_incident_ids.map((matchId) => {
                      if (canAccessOperatorLinks) {
                        return (
                          <Link
                            key={matchId}
                            to={`/incidents/${matchId}`}
                            className="inline-flex items-center space-x-1 text-xs font-mono font-medium text-blue-700 bg-white px-2 py-0.5 rounded border border-blue-200 hover:bg-blue-50 transition-colors"
                          >
                            <span>{matchId.substring(0, 8)}...</span>
                            <ExternalLink className="h-3 w-3" aria-hidden="true" />
                          </Link>
                        );
                      }
                      return (
                        <span
                          key={matchId}
                          className="inline-flex items-center font-mono text-xs text-slate-600 bg-white px-2 py-0.5 rounded border border-slate-200"
                        >
                          {matchId.substring(0, 8)}...
                        </span>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
