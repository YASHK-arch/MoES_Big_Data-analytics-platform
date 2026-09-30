import React, { useState, useEffect } from 'react';
import {
  X,
  Clock,
  MapPin,
  ArrowRight,
  ShieldAlert,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { ReportDetailData, IncidentDetailPublic } from '@/types';
import { MapIncidentPoint } from '@/features/map/adapters';

interface SelectedIncidentCardProps {
  report: ReportDetailData | IncidentDetailPublic | MapIncidentPoint;
  isLoadingDetail?: boolean;
  onClose: () => void;
}

export const SelectedIncidentCard: React.FC<SelectedIncidentCardProps> = ({
  report,
  isLoadingDetail = false,
  onClose,
}) => {
  const [mediaError, setMediaError] = useState<boolean>(false);

  // Reset media error state when selected report changes
  useEffect(() => {
    setMediaError(false);
  }, [report.id, report.tracking_id]);

  const verificationStatus =
    'verification_status' in report && typeof report.verification_status === 'string'
      ? report.verification_status
      : 'verification' in report && report.verification?.status
      ? report.verification.status
      : 'PENDING';

  const isVerified =
    verificationStatus === 'VERIFIED' ||
    ('verification' in report && Boolean(report.verification?.is_verified));
  const isUnderReview =
    verificationStatus === 'UNDER_REVIEW' ||
    ('verification' in report && Boolean(report.verification?.is_under_review));

  const formatReportTime = (dateStr?: string | null) => {
    if (!dateStr) return 'Recent';
    try {
      const d = new Date(dateStr);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false }) + ' IST';
    } catch {
      return 'Recent';
    }
  };

  const mediaList = 'media' in report && Array.isArray(report.media) ? report.media : [];
  const firstMedia = mediaList.length > 0 ? mediaList[0] : null;
  const isVideo = firstMedia?.media_type === 'VIDEO';
  const description = 'description' in report ? report.description : null;
  const categoryTitle = report.category?.title || 'Weather Incident';

  return (
    <div className="rounded-2xl border border-slate-200/90 bg-white shadow-2xl overflow-hidden w-full max-w-sm sm:max-w-md animate-in fade-in slide-in-from-bottom-4 duration-200">
      {/* Top Media Header / Fallback Banner */}
      <div className="relative h-44 bg-slate-900 overflow-hidden group">
        {firstMedia && !mediaError ? (
          isVideo ? (
            <video
              src={firstMedia.url}
              controls
              className="h-full w-full object-cover bg-black"
              onError={() => setMediaError(true)}
            />
          ) : (
            <a
              href={firstMedia.url}
              target="_blank"
              rel="noopener noreferrer"
              title="Click to view full image in new tab"
              className="block h-full w-full relative cursor-pointer"
            >
              <img
                src={firstMedia.url}
                alt={report.title}
                loading="lazy"
                className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
                onError={() => setMediaError(true)}
              />
              <div className="absolute inset-0 bg-black/20 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                <span className="flex items-center space-x-1 rounded-lg bg-slate-900/80 px-2.5 py-1 text-[11px] font-semibold text-white backdrop-blur-sm shadow-md">
                  <ExternalLink className="h-3 w-3" />
                  <span>View Full Image</span>
                </span>
              </div>
            </a>
          )
        ) : (
          <div className="h-full w-full flex items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-indigo-950 text-white/80 p-4">
            <div className="flex flex-col items-center text-center">
              <ShieldAlert className="h-9 w-9 text-blue-400 mb-1.5 opacity-90" />
              <span className="text-xs font-semibold uppercase tracking-wider text-blue-200">
                {categoryTitle}
              </span>
              {isLoadingDetail && (
                <span className="text-[10px] text-blue-300 mt-1 animate-pulse">
                  Loading incident media...
                </span>
              )}
              {mediaError && (
                <span className="text-[10px] text-slate-400 mt-1">
                  Attached media preview unavailable
                </span>
              )}
            </div>
          </div>
        )}

        {/* Demo Badge */}
        {Boolean('is_demo' in report && report.is_demo) && (
          <div className="absolute top-3 left-3 z-10">
            <span
              className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-extrabold uppercase shadow-md bg-amber-500 text-white"
              data-testid="demo-badge"
            >
              DEMO
            </span>
          </div>
        )}

        {/* Verification Status Pill */}
        <div className="absolute top-3 right-3 z-10">
          <span
            className={`inline-flex items-center space-x-1 rounded-full px-2.5 py-0.5 text-xs font-bold shadow-md backdrop-blur-sm ${
              isVerified
                ? 'bg-emerald-600/95 text-white'
                : isUnderReview
                ? 'bg-amber-500/95 text-white'
                : 'bg-blue-600/95 text-white'
            }`}
          >
            {isVerified ? (
              <CheckCircle2 className="h-3 w-3" />
            ) : (
              <AlertCircle className="h-3 w-3" />
            )}
            <span>{verificationStatus}</span>
          </span>
        </div>

        {/* Close Button */}
        <button
          type="button"
          onClick={onClose}
          aria-label="Close incident details"
          className="absolute top-3 left-3 z-10 rounded-full bg-slate-900/70 p-1.5 text-white hover:bg-slate-900 focus:outline-none focus:ring-2 focus:ring-white transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Incident Content */}
      <div className="p-4 sm:p-5">
        <div className="flex items-start justify-between">
          <h2 className="text-base sm:text-lg font-bold text-slate-900 leading-snug">
            {report.title}
          </h2>
        </div>

        <div className="mt-3 space-y-2 text-xs text-slate-600">
          <div className="flex items-center space-x-2">
            <Clock className="h-3.5 w-3.5 text-slate-400 shrink-0" />
            <span>
              Reported:{' '}
              {formatReportTime(
                report.occurred_at || ('created_at' in report ? report.created_at : null)
              )}
            </span>
          </div>

          <div className="flex items-center space-x-2">
            <MapPin className="h-3.5 w-3.5 text-blue-600 shrink-0" />
            <span className="font-semibold text-slate-800">
              {report.location?.name || 'Reported Location'}
            </span>
          </div>
        </div>

        {/* Coordinates bar */}
        <div className="mt-3 rounded-lg border border-slate-100 bg-slate-50 px-3 py-1.5 font-mono text-[11px] text-slate-500 flex justify-between">
          <span>Lat: {report.location?.latitude?.toFixed(4)}</span>
          <span>Lng: {report.location?.longitude?.toFixed(4)}</span>
        </div>

        {description && (
          <p className="mt-3 text-xs text-slate-600 line-clamp-2 leading-relaxed">
            {description}
          </p>
        )}

        {/* Action Button linking to Track Report */}
        <div className="mt-4 pt-3 border-t border-slate-100">
          <Link
            to={`/track-report?id=${encodeURIComponent(report.tracking_id)}`}
            className="flex w-full items-center justify-center space-x-2 rounded-xl bg-blue-600 py-2.5 text-xs font-bold text-white shadow-md transition-all hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-600/30"
          >
            <span>View Details</span>
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      </div>
    </div>
  );
};
