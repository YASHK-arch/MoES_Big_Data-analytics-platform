import React, { useState, useEffect } from 'react';
import {
  X,
  Clock,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Copy,
  Info,
  Radio,
  ImageOff,
  History,
  CornerDownRight,
} from 'lucide-react';
import { MapContainer, TileLayer, Marker } from 'react-leaflet';
import L from 'leaflet';
import { ReportDetailData } from '@/types';
import {
  verifyReport,
  rejectReport,
  markDuplicateReport,
  placeReportUnderReview,
} from '@/services/reportApi';

interface ReviewReportDrawerProps {
  report: ReportDetailData | null;
  onClose: () => void;
  onActionComplete: () => void;
}

const miniMarkerIcon = L.divIcon({
  className: 'custom-mini-marker',
  html: `<div style="
    width: 20px;
    height: 20px;
    background-color: #2563eb;
    border: 2.5px solid #ffffff;
    border-radius: 50%;
    box-shadow: 0 2px 6px rgba(0,0,0,0.3);
  "></div>`,
  iconSize: [20, 20],
  iconAnchor: [10, 10],
});

export const ReviewReportDrawer: React.FC<ReviewReportDrawerProps> = ({
  report,
  onClose,
  onActionComplete,
}) => {
  const [notes, setNotes] = useState('');
  const [rejectionReason, setRejectionReason] = useState('INACCURATE_LOCATION');
  const [duplicatePrimaryId, setDuplicatePrimaryId] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [showRejectForm, setShowRejectForm] = useState(false);
  const [showDuplicateForm, setShowDuplicateForm] = useState(false);

  useEffect(() => {
    // Reset local form states when report changes
    setNotes('');
    setRejectionReason('INACCURATE_LOCATION');
    setDuplicatePrimaryId('');
    setActionError(null);
    setActionSuccess(null);
    setShowRejectForm(false);
    setShowDuplicateForm(false);
  }, [report?.id]);

  if (!report) return null;

  const isVerified = report.verification_status === 'VERIFIED';
  const isRejected = report.verification_status === 'REJECTED';
  const isDuplicate = report.verification_status === 'DUPLICATE';
  const isTerminal = isVerified || isRejected || isDuplicate;

  const hasMedia = report.media && report.media.length > 0;
  const mediaItem = hasMedia ? report.media[0] : null;

  const formatReportedTime = (dateStr: string) => {
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString([], {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return dateStr;
    }
  };

  const handleVerify = async () => {
    setIsSubmitting(true);
    setActionError(null);
    try {
      await verifyReport(report.id, notes, true);
      setActionSuccess('Report successfully authorized as VERIFIED.');
      setTimeout(() => {
        onActionComplete();
      }, 700);
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Failed to verify report.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReject = async () => {
    setIsSubmitting(true);
    setActionError(null);
    try {
      await rejectReport(report.id, rejectionReason, notes);
      setActionSuccess('Report marked as REJECTED.');
      setTimeout(() => {
        onActionComplete();
      }, 700);
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Failed to reject report.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDuplicate = async () => {
    setIsSubmitting(true);
    setActionError(null);
    try {
      await markDuplicateReport(report.id, duplicatePrimaryId || undefined, notes);
      setActionSuccess('Report marked as DUPLICATE.');
      setTimeout(() => {
        onActionComplete();
      }, 700);
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Failed to mark duplicate.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleUnderReview = async () => {
    setIsSubmitting(true);
    setActionError(null);
    try {
      await placeReportUnderReview(report.id, notes);
      setActionSuccess('Report marked as UNDER REVIEW.');
      setTimeout(() => {
        onActionComplete();
      }, 700);
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Failed to place under review.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex h-full flex-col bg-white overflow-hidden">
      {/* 1. Drawer Header (Fixed at top) */}
      <div className="flex-shrink-0 flex items-center justify-between border-b border-slate-200 px-6 py-3.5 bg-slate-50/50">
        <div>
          <h2 className="text-base font-bold text-slate-900">Review Report</h2>
          <span className="font-mono text-xs font-bold text-slate-500">
            {report.tracking_id}
          </span>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close review panel"
          className="rounded-xl p-1.5 text-slate-400 hover:bg-slate-200/70 hover:text-slate-700 transition-colors cursor-pointer"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* 2. Drawer Body (Scrollable Middle) */}
      <div className="flex-1 min-h-0 overflow-y-auto p-6 space-y-5">
        {/* Action feedback banners */}
        {actionSuccess && (
          <div className="rounded-xl bg-emerald-50 border border-emerald-200 p-3 text-xs font-semibold text-emerald-800 flex items-center space-x-2">
            <CheckCircle2 className="h-4 w-4 text-emerald-600 flex-shrink-0" />
            <span>{actionSuccess}</span>
          </div>
        )}

        {actionError && (
          <div className="rounded-xl bg-rose-50 border border-rose-200 p-3 text-xs font-semibold text-rose-800 flex items-center space-x-2">
            <AlertTriangle className="h-4 w-4 text-rose-600 flex-shrink-0" />
            <span>{actionError}</span>
          </div>
        )}

        {/* Evidence Image / Video Preview */}
        <div>
          {mediaItem?.url ? (
            <div className="relative rounded-2xl overflow-hidden border border-slate-200 bg-slate-900 shadow-sm">
              {mediaItem.media_type === 'VIDEO' ? (
                <video
                  src={mediaItem.url}
                  controls
                  className="h-52 w-full object-cover"
                />
              ) : (
                <img
                  src={mediaItem.url}
                  alt={report.title}
                  className="h-52 w-full object-cover"
                  onError={(e) => {
                    (e.target as HTMLElement).style.display = 'none';
                  }}
                />
              )}
              <div className="absolute bottom-2.5 right-2.5 rounded-lg bg-black/70 px-2.5 py-1 text-[10px] font-semibold text-white backdrop-blur-xs">
                Source: Citizen Web / Mobile App
              </div>
            </div>
          ) : (
            <div className="flex h-32 w-full flex-col items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-50 text-slate-400">
              <ImageOff className="h-7 w-7 mb-1" />
              <span className="text-xs font-medium">No media attached</span>
            </div>
          )}
        </div>

        {/* Event Type & Reported Time */}
        <div className="grid grid-cols-2 gap-3 rounded-2xl border border-slate-100 bg-slate-50/70 p-3.5">
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
              Event Type
            </span>
            <div className="mt-1 flex items-center space-x-1.5 text-xs font-bold text-slate-900">
              <AlertTriangle className="h-4 w-4 text-blue-600" />
              <span>{report.category?.title || report.title}</span>
            </div>
          </div>

          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
              Reported Time
            </span>
            <div className="mt-1 flex items-center space-x-1.5 text-xs font-bold text-slate-900">
              <Clock className="h-4 w-4 text-slate-500" />
              <span>{formatReportedTime(report.occurred_at || report.created_at)}</span>
            </div>
          </div>
        </div>

        {/* Title & Description */}
        <div>
          <h3 className="text-sm font-bold text-slate-900">{report.title}</h3>
          {report.description && (
            <p className="mt-1.5 text-xs text-slate-600 leading-relaxed whitespace-pre-wrap">
              {report.description}
            </p>
          )}
        </div>

        {/* Location Context & Mini Map */}
        <div className="space-y-2">
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
            Location Context
          </span>
          <div className="text-xs font-semibold text-slate-800">
            {report.location?.name || 'Reported Location'}
          </div>
          <div className="font-mono text-[11px] text-slate-500">
            Coordinates: {report.location?.latitude.toFixed(4)}° N,{' '}
            {report.location?.longitude.toFixed(4)}° E
          </div>

          {/* Mini Leaflet Map Widget */}
          <div className="h-32 w-full rounded-2xl overflow-hidden border border-slate-200 shadow-2xs">
            <MapContainer
              center={[report.location.latitude, report.location.longitude]}
              zoom={12}
              scrollWheelZoom={false}
              zoomControl={false}
              attributionControl={false}
              className="h-full w-full"
            >
              <TileLayer
                url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
                maxZoom={18}
              />
              <Marker
                position={[report.location.latitude, report.location.longitude]}
                icon={miniMarkerIcon}
              />
            </MapContainer>
          </div>
        </div>

        {/* Meteorological Corroboration (Data-Honest State) */}
        <div className="rounded-2xl border border-slate-200 bg-slate-50/50 p-4 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-1.5">
              <Radio className="h-4 w-4 text-slate-400" />
              <span className="text-xs font-bold text-slate-700">
                Meteorological Corroboration
              </span>
            </div>
            <span className="rounded-md bg-slate-200/80 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-slate-600">
              Awaiting AWS
            </span>
          </div>
          <p className="text-[11px] text-slate-500 leading-relaxed">
            Automated meteorological corroboration engine is not yet attached to live AWS sensors.
            Ground truth status remains pending manual operator triage.
          </p>
        </div>

        {/* Credibility Assessment (Data-Honest State) */}
        <div className="rounded-2xl border border-slate-200 bg-slate-50/50 p-4 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-700">
              Credibility Assessment
            </span>
            {report.credibility_score > 0 ? (
              <span className="font-mono text-xs font-extrabold text-emerald-600">
                {(report.credibility_score * 100).toFixed(0)}% Score
              </span>
            ) : (
              <span className="text-[11px] text-slate-400 italic">
                Not Yet Calculated
              </span>
            )}
          </div>
          <p className="text-[11px] text-slate-600 leading-relaxed font-medium bg-white p-2.5 rounded-lg border border-slate-200/60 mt-2">
            {report.credibility_reason ||
              (report.credibility_score > 0
                ? 'Algorithmic credibility score computed from metadata and corroboration factors.'
                : 'Statistical credibility scoring pipeline not yet executed for this report.')}
          </p>
        </div>

        {/* Verification History Audit Trail */}
        {report.verification_history && report.verification_history.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center space-x-1.5 text-xs font-bold text-slate-700">
              <History className="h-4 w-4 text-blue-600" />
              <span>Verification History</span>
            </div>
            <div className="space-y-2">
              {report.verification_history.map((ev) => (
                <div
                  key={ev.id}
                  className="rounded-xl border border-slate-200 bg-white p-3 text-xs shadow-2xs"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-slate-800">
                      {ev.new_status}
                    </span>
                    <span className="font-mono text-[10px] text-slate-400">
                      {formatReportedTime(ev.created_at)}
                    </span>
                  </div>
                  <div className="mt-1 text-slate-600 text-[11px]">
                    Action recorded by <span className="font-semibold text-slate-800">{ev.reviewer_name}</span>
                  </div>
                  {ev.notes && (
                    <div className="mt-1.5 rounded-lg bg-slate-50 p-2 text-slate-700 text-[11px] italic">
                      "{ev.notes}"
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Operator Notes Input Area (Active triage only) */}
        {!isTerminal && (
          <div className="space-y-1.5">
            <label
              htmlFor="operator-notes"
              className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center space-x-1"
            >
              <span>Operator Notes</span>
            </label>
            <textarea
              id="operator-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              placeholder="Add verification context, agency dispatch notes, or reason for decision..."
              className="w-full rounded-xl border border-slate-200 bg-slate-50/70 p-3 text-xs text-slate-800 placeholder-slate-400 focus:border-blue-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition-colors"
            />
          </div>
        )}
      </div>

      {/* 3. Drawer Action Footer (Fixed & Sticky at Bottom) */}
      <div className="flex-shrink-0 border-t border-slate-200 bg-white p-4 shadow-xl space-y-2.5">
        {isTerminal ? (
          <div className="space-y-2">
            {isVerified && (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50/80 p-3.5 flex items-center space-x-3 text-emerald-900">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-100 text-emerald-700 shrink-0">
                  <CheckCircle2 className="h-5 w-5" />
                </div>
                <div>
                  <div className="text-xs font-bold text-emerald-900">Ground Truth Verified</div>
                  <div className="text-[11px] text-emerald-700 font-medium">Verification completed</div>
                </div>
              </div>
            )}

            {isRejected && (
              <div className="rounded-xl border border-rose-200 bg-rose-50/80 p-3.5 flex items-center space-x-3 text-rose-900">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-rose-100 text-rose-700 shrink-0">
                  <XCircle className="h-5 w-5" />
                </div>
                <div>
                  <div className="text-xs font-bold text-rose-900">Incident Rejected</div>
                  <div className="text-[11px] text-rose-700 font-medium">Verification closed</div>
                </div>
              </div>
            )}

            {isDuplicate && (
              <div className="rounded-xl border border-purple-200 bg-purple-50/80 p-3.5 flex items-center space-x-3 text-purple-900">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-purple-100 text-purple-700 shrink-0">
                  <Copy className="h-5 w-5" />
                </div>
                <div>
                  <div className="text-xs font-bold text-purple-900">Marked as Duplicate</div>
                  <div className="text-[11px] text-purple-700 font-medium">Verification closed</div>
                </div>
              </div>
            )}
          </div>
        ) : (
          <>
            {/* Inline Reject Options Expansion */}
            {showRejectForm && (
              <div className="rounded-xl border border-rose-200 bg-rose-50/80 p-3 space-y-2 animate-in fade-in duration-150">
                <div className="flex items-center justify-between">
                  <label className="text-[11px] font-bold text-rose-900">
                    Select Rejection Reason:
                  </label>
                  <button
                    type="button"
                    onClick={() => setShowRejectForm(false)}
                    className="text-[10px] font-bold text-slate-500 hover:text-slate-800 cursor-pointer"
                  >
                    Cancel
                  </button>
                </div>
                <select
                  value={rejectionReason}
                  onChange={(e) => setRejectionReason(e.target.value)}
                  className="w-full rounded-lg border border-rose-200 bg-white p-2 text-xs font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-rose-500/20"
                >
                  <option value="INACCURATE_LOCATION">Inaccurate / Fake Location</option>
                  <option value="OLD_ARCHIVED_MEDIA">Old or Archived Photo</option>
                  <option value="SPAM_HOAX">Spam or Hoax Submission</option>
                  <option value="METEOROLOGICALLY_IMPOSSIBLE">Meteorologically Inconsistent</option>
                  <option value="OTHER">Other Reason</option>
                </select>
                <button
                  type="button"
                  onClick={handleReject}
                  disabled={isSubmitting}
                  className="w-full rounded-xl bg-rose-600 py-2.5 text-xs font-bold text-white hover:bg-rose-700 disabled:opacity-60 transition-colors cursor-pointer shadow-xs"
                >
                  {isSubmitting ? 'Rejecting...' : 'Confirm Rejection'}
                </button>
              </div>
            )}

            {/* Inline Duplicate Options Expansion */}
            {showDuplicateForm && (
              <div className="rounded-xl border border-purple-200 bg-purple-50/80 p-3 space-y-2 animate-in fade-in duration-150">
                <div className="flex items-center justify-between">
                  <label className="text-[11px] font-bold text-purple-900">
                    Primary Report Tracking ID (Optional):
                  </label>
                  <button
                    type="button"
                    onClick={() => setShowDuplicateForm(false)}
                    className="text-[10px] font-bold text-slate-500 hover:text-slate-800 cursor-pointer"
                  >
                    Cancel
                  </button>
                </div>
                <input
                  type="text"
                  value={duplicatePrimaryId}
                  onChange={(e) => setDuplicatePrimaryId(e.target.value)}
                  placeholder="e.g. RPT-20260829-K8L9"
                  className="w-full rounded-lg border border-purple-200 bg-white p-2 text-xs font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-purple-500/20"
                />
                <button
                  type="button"
                  onClick={handleDuplicate}
                  disabled={isSubmitting}
                  className="w-full rounded-xl bg-purple-600 py-2.5 text-xs font-bold text-white hover:bg-purple-700 disabled:opacity-60 transition-colors cursor-pointer shadow-xs"
                >
                  {isSubmitting ? 'Marking Duplicate...' : 'Confirm Mark as Duplicate'}
                </button>
              </div>
            )}

            {/* Primary Action Buttons (Matching Stitch Reference) */}
            {!showRejectForm && !showDuplicateForm && (
              <>
                <div className="flex items-center space-x-2">
                  {/* Verify Report Button */}
                  <button
                    type="button"
                    onClick={handleVerify}
                    disabled={isSubmitting}
                    className="flex-1 flex items-center justify-center space-x-2 rounded-xl bg-blue-600 py-3 px-4 text-xs font-bold text-white shadow-sm hover:bg-blue-700 disabled:opacity-60 transition-all cursor-pointer"
                  >
                    <CheckCircle2 className="h-4 w-4" />
                    <span>{isSubmitting ? 'Verifying...' : 'Verify Report'}</span>
                  </button>

                  {/* Reject Button */}
                  <button
                    type="button"
                    onClick={() => {
                      setShowRejectForm(true);
                      setShowDuplicateForm(false);
                    }}
                    disabled={isSubmitting}
                    className="flex items-center justify-center space-x-1.5 rounded-xl border border-rose-300 bg-white py-3 px-4 text-xs font-bold text-rose-700 shadow-2xs hover:bg-rose-50 disabled:opacity-60 transition-all cursor-pointer"
                  >
                    <XCircle className="h-4 w-4" />
                    <span>Reject</span>
                  </button>
                </div>

                {/* Mark as Duplicate Full Width Button */}
                <button
                  type="button"
                  onClick={() => {
                    setShowDuplicateForm(true);
                    setShowRejectForm(false);
                  }}
                  disabled={isSubmitting}
                  className="w-full flex items-center justify-center space-x-1.5 rounded-xl border border-slate-200 bg-slate-50/80 py-2.5 px-3 text-xs font-bold text-slate-700 hover:bg-slate-100 disabled:opacity-60 transition-colors cursor-pointer"
                >
                  <Copy className="h-3.5 w-3.5" />
                  <span>Mark as Duplicate</span>
                </button>

                {/* Keep Under Review Option */}
                <button
                  type="button"
                  onClick={handleUnderReview}
                  disabled={isSubmitting}
                  className="w-full flex items-center justify-center space-x-1 text-[11px] font-semibold text-slate-500 hover:text-amber-700 transition-colors cursor-pointer py-1"
                >
                  <Info className="h-3 w-3 text-amber-500" />
                  <span>Keep Under Review</span>
                  <CornerDownRight className="h-3 w-3 text-slate-400" />
                </button>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
};
