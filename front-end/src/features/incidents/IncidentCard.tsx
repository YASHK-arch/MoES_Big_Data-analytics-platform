// Reusable Unified Incident Card Component

import React from 'react';
import { Link } from 'react-router-dom';
import {
  MapPin,
  Clock,
  ExternalLink,
  Sparkles,
} from 'lucide-react';
import { IncidentSummary } from '@/types';
import {
  formatHazardCategory,
  formatRelativeTime,
  formatSeverityBadge,
  formatVerificationStatus,
  formatReadiness,
} from '@/lib/presentation';

interface IncidentCardProps {
  incident: IncidentSummary;
  isSelected?: boolean;
  onSelect?: (incident: IncidentSummary) => void;
  className?: string;
}

export const IncidentCard: React.FC<IncidentCardProps> = ({
  incident,
  isSelected = false,
  onSelect,
  className = '',
}) => {
  const severityStyle = formatSeverityBadge(incident.severity);
  const verificationStyle = formatVerificationStatus(incident.verification_status);
  const readinessStyle = formatReadiness(incident.readiness);

  const credScoreValue =
    incident.credibility_score != null
      ? Math.round(incident.credibility_score * 100)
      : null;

  return (
    <article
      onClick={() => onSelect?.(incident)}
      className={`rounded-2xl border p-4.5 transition-all cursor-pointer bg-white shadow-2xs hover:shadow-md hover:border-slate-300 ${
        isSelected
          ? 'border-blue-500 bg-blue-50/30 ring-2 ring-blue-500/20'
          : 'border-slate-200/80'
      } ${className}`}
      aria-label={`Incident: ${incident.title}`}
    >
      {/* Top Meta Bar */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center space-x-2">
          <span
            className={`inline-flex items-center rounded-lg px-2 py-0.5 text-[11px] font-bold border ${severityStyle.bgClass} ${severityStyle.borderClass}`}
          >
            {formatHazardCategory(incident.category?.code)}
          </span>
          <span
            className={`inline-flex items-center rounded-lg px-2 py-0.5 text-[10px] font-extrabold ${verificationStyle.bgClass}`}
          >
            {verificationStyle.label}
          </span>
          {incident.is_demo && (
            <span
              className="inline-flex items-center rounded-lg px-2 py-0.5 text-[10px] font-extrabold uppercase bg-amber-100 text-amber-800 border border-amber-300"
              data-testid="demo-badge"
            >
              DEMO
            </span>
          )}
        </div>

        <div className="flex items-center space-x-1 text-[11px] font-medium text-slate-400">
          <Clock className="h-3 w-3" aria-hidden="true" />
          <time dateTime={incident.occurred_at || incident.created_at}>
            {formatRelativeTime(incident.occurred_at || incident.created_at)}
          </time>
        </div>
      </div>

      {/* Incident Title */}
      <h3 className="text-sm sm:text-base font-bold text-slate-900 mt-2.5 leading-snug line-clamp-2">
        {incident.title}
      </h3>

      {/* Location Badge */}
      <div className="mt-2 flex items-center space-x-1.5 text-xs text-slate-600">
        <MapPin className="h-3.5 w-3.5 text-blue-600 shrink-0" aria-hidden="true" />
        <span className="font-medium truncate">
          {incident.location?.name ?? (incident.location?.latitude != null ? `${incident.location.latitude.toFixed(3)}, ${incident.location.longitude?.toFixed(3)}` : 'Location Pending')}
        </span>
      </div>

      {/* Intelligence & Credibility Bar */}
      <div className="mt-3.5 pt-3 border-t border-slate-100 flex items-center justify-between gap-2 flex-wrap text-xs">
        {/* Machine Credibility Display */}
        <div className="flex items-center space-x-1.5" title="Machine-Assessed Credibility Score">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-indigo-50 text-indigo-600">
            <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
          </div>
          <div>
            <span className="text-[11px] font-extrabold text-slate-900">
              {credScoreValue != null ? `${credScoreValue} / 100` : 'Assessing...'}
            </span>
            <span className="text-[9px] text-slate-400 block -mt-0.5">Credibility</span>
          </div>
        </div>

        {/* Readiness Pill */}
        <span
          className={`inline-flex items-center space-x-1 rounded-full px-2 py-0.5 text-[10px] font-bold border ${readinessStyle.badgeClass}`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${readinessStyle.pillBg}`} aria-hidden="true" />
          <span>{readinessStyle.label}</span>
        </span>
      </div>

      {/* Footer Navigation */}
      <div className="mt-3 flex items-center justify-between text-[11px] text-slate-500 pt-2 border-t border-slate-50">
        <span className="font-mono text-[10px] text-slate-400">
          {incident.tracking_id}
        </span>
        <Link
          to={`/incidents/${encodeURIComponent(incident.id || incident.tracking_id)}`}
          onClick={(e) => e.stopPropagation()}
          className="inline-flex items-center space-x-1 font-bold text-blue-600 hover:text-blue-800 transition-colors"
        >
          <span>Inspect Intelligence</span>
          <ExternalLink className="h-3 w-3" aria-hidden="true" />
        </Link>
      </div>
    </article>
  );
};
