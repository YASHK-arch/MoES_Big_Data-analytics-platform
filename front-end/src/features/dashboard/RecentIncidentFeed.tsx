// Dashboard Recent Incident Feed Component

import React from 'react';
import { ListFilter, ExternalLink, ArrowRight, Sparkles, MapPin } from 'lucide-react';
import { Link } from 'react-router-dom';
import { IncidentSummary, ReportDetailData } from '@/types';
import { MapIncidentPoint } from '@/features/map/adapters';
import {
  formatHazardCategory,
  formatRelativeTime,
  formatSeverityBadge,
  formatVerificationStatus,
} from '@/lib/presentation';

interface RecentIncidentFeedProps {
  reports: (IncidentSummary | ReportDetailData)[];
  totalCount?: number;
  selectedReport: IncidentSummary | ReportDetailData | MapIncidentPoint | null;
  onSelectReport: (report: IncidentSummary | ReportDetailData) => void;
  isLoading: boolean;
}

export const RecentIncidentFeed: React.FC<RecentIncidentFeedProps> = ({
  reports,
  totalCount,
  selectedReport,
  onSelectReport,
  isLoading,
}) => {
  const displayReports = reports.slice(0, 6);

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-2xs overflow-hidden flex flex-col h-full">
      {/* Feed Header */}
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-100 bg-white">
        <div className="flex items-center space-x-2">
          <ListFilter className="h-4 w-4 text-blue-600" aria-hidden="true" />
          <h3 className="text-sm font-bold text-slate-900">Current Incident Feed</h3>
        </div>
        <div className="flex items-center space-x-1.5">
          <div className="h-2 w-2 rounded-full bg-blue-600 animate-pulse" aria-hidden="true" />
          <span className="text-xs text-slate-500 font-semibold">{totalCount ?? reports.length} Incidents</span>
        </div>
      </div>

      {/* Feed List Body */}
      <div className="p-4 flex-1 overflow-y-auto space-y-3 max-h-[500px]">
        {isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-24 rounded-xl border border-slate-100 bg-slate-50 p-3 animate-pulse">
                <div className="h-3 w-20 bg-slate-200 rounded" />
                <div className="h-4 w-40 bg-slate-200 rounded mt-2" />
                <div className="h-3 w-full bg-slate-100 rounded mt-2" />
              </div>
            ))}
          </div>
        ) : displayReports.length === 0 ? (
          <div className="py-12 text-center text-slate-500">
            <p className="text-xs font-semibold">No incident reports found matching current filters.</p>
          </div>
        ) : (
          displayReports.map((report) => {
            const isSelected = selectedReport?.tracking_id === report.tracking_id;
            const categoryCode = typeof report.category === 'object' ? report.category?.code : undefined;
            const categoryTitle = typeof report.category === 'object' ? report.category?.title : formatHazardCategory(categoryCode);
            const severityStyle = formatSeverityBadge(report.severity);
            const verificationStyle = formatVerificationStatus(report.verification_status);

            const credScore = report.credibility_score != null ? Math.round(report.credibility_score * 100) : null;

            return (
              <div
                key={report.id || report.tracking_id}
                onClick={() => onSelectReport(report)}
                className={`rounded-xl border p-3.5 transition-all cursor-pointer ${
                  isSelected
                    ? 'border-blue-500 bg-blue-50/40 ring-2 ring-blue-500/20 shadow-sm'
                    : 'border-slate-200/80 bg-white hover:border-slate-300 hover:bg-slate-50/60 shadow-2xs'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-1.5">
                    <span className={`text-[10px] font-extrabold uppercase tracking-wider ${severityStyle.textClass}`}>
                      {categoryTitle}
                    </span>
                    <span className={`rounded px-1.5 py-0.2 text-[9px] font-extrabold ${verificationStyle.bgClass}`}>
                      {verificationStyle.label}
                    </span>
                  </div>
                  <span className="text-[10px] font-medium text-slate-400">
                    {formatRelativeTime(report.occurred_at || report.created_at)}
                  </span>
                </div>

                <h4 className="text-xs sm:text-sm font-bold text-slate-900 mt-1.5 line-clamp-1">
                  {report.title}
                </h4>

                <div className="mt-1 flex items-center space-x-1 text-[11px] text-slate-500">
                  <MapPin className="h-3 w-3 text-blue-600 shrink-0" aria-hidden="true" />
                  <span className="truncate">{report.location?.name || 'Reported Area'}</span>
                </div>

                <div className="mt-2.5 flex flex-col space-y-1 pt-2 border-t border-slate-100 text-[10px]">
                  <div className="flex items-center justify-between">
                    {credScore != null && (
                      <div className="flex items-center space-x-1 text-slate-700 font-bold">
                        <Sparkles className="h-3 w-3 text-indigo-600 shrink-0" aria-hidden="true" />
                        <span>Credibility: {credScore} / 100</span>
                      </div>
                    )}

                    <Link
                      to={`/incidents/${encodeURIComponent(report.id || report.tracking_id)}`}
                      onClick={(e) => e.stopPropagation()}
                      className="flex items-center space-x-1 text-[10px] font-bold text-blue-600 hover:text-blue-800 ml-auto"
                    >
                      <span>Inspect</span>
                      <ExternalLink className="h-3 w-3" aria-hidden="true" />
                    </Link>
                  </div>

                  {report.credibility_reason && (
                    <p className="text-[10px] text-slate-500 font-normal line-clamp-1 italic">
                      Reason: {report.credibility_reason}
                    </p>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Feed Footer */}
      <div className="p-3 border-t border-slate-100 bg-slate-50/50">
        <Link
          to="/incidents"
          className="flex w-full items-center justify-center space-x-1.5 rounded-xl bg-white py-2 text-xs font-bold text-blue-600 border border-slate-200 shadow-2xs hover:bg-slate-50 hover:border-slate-300 transition-colors"
        >
          <span>Explore All Incidents</span>
          <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
        </Link>
      </div>
    </div>
  );
};
