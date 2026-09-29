import React from 'react';
import { ImageOff, ChevronRight, CheckSquare, Square } from 'lucide-react';
import { ReportDetailData } from '@/types';

interface QueueTableProps {
  reports: ReportDetailData[];
  selectedReport: ReportDetailData | null;
  onSelectReport: (report: ReportDetailData) => void;
  selectedIds: Set<string>;
  onToggleSelectId: (id: string) => void;
  onToggleSelectAll: () => void;
  isLoading: boolean;
}

export const QueueTable: React.FC<QueueTableProps> = ({
  reports,
  selectedReport,
  onSelectReport,
  selectedIds,
  onToggleSelectId,
  onToggleSelectAll,
  isLoading,
}) => {
  const isAllSelected = reports.length > 0 && selectedIds.size === reports.length;

  const formatReportTime = (dateStr: string) => {
    try {
      const d = new Date(dateStr);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return dateStr;
    }
  };

  const getSeverityBadge = (severity: string) => {
    const sev = severity.toUpperCase();
    if (sev === 'SEVERE' || sev === 'CRITICAL') {
      return (
        <span className="inline-flex items-center rounded-md bg-red-50 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wider text-red-700 border border-red-200">
          Critical
        </span>
      );
    }
    if (sev === 'HIGH') {
      return (
        <span className="inline-flex items-center rounded-md bg-amber-50 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wider text-amber-700 border border-amber-200">
          High
        </span>
      );
    }
    if (sev === 'MODERATE') {
      return (
        <span className="inline-flex items-center rounded-md bg-blue-50 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wider text-blue-700 border border-blue-200">
          Moderate
        </span>
      );
    }
    return (
      <span className="inline-flex items-center rounded-md bg-slate-50 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wider text-slate-700 border border-slate-200">
        Low
      </span>
    );
  };

  const getStatusBadge = (status: string) => {
    const s = status.toUpperCase();
    if (s === 'VERIFIED') {
      return (
        <span className="inline-flex items-center rounded-full bg-emerald-50 px-2.5 py-0.5 text-[11px] font-bold text-emerald-700 border border-emerald-200">
          Verified
        </span>
      );
    }
    if (s === 'UNDER_REVIEW') {
      return (
        <span className="inline-flex items-center rounded-full bg-amber-50 px-2.5 py-0.5 text-[11px] font-bold text-amber-700 border border-amber-200">
          Under Review
        </span>
      );
    }
    if (s === 'REJECTED') {
      return (
        <span className="inline-flex items-center rounded-full bg-rose-50 px-2.5 py-0.5 text-[11px] font-bold text-rose-700 border border-rose-200">
          Rejected
        </span>
      );
    }
    if (s === 'DUPLICATE') {
      return (
        <span className="inline-flex items-center rounded-full bg-purple-50 px-2.5 py-0.5 text-[11px] font-bold text-purple-700 border border-purple-200">
          Duplicate
        </span>
      );
    }
    return (
      <span className="inline-flex items-center rounded-full bg-blue-50 px-2.5 py-0.5 text-[11px] font-bold text-blue-700 border border-blue-200">
        Pending
      </span>
    );
  };

  if (isLoading) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="space-y-4 animate-pulse">
          <div className="h-10 bg-slate-100 rounded-xl" />
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-14 bg-slate-50 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  if (reports.length === 0) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-12 text-center shadow-sm">
        <p className="text-sm font-semibold text-slate-700">
          No reports matching the selected filters.
        </p>
        <p className="mt-1 text-xs text-slate-500">
          Try adjusting status, category, or search query.
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs text-slate-600">
          {/* Table Header */}
          <thead className="border-b border-slate-200 bg-slate-50/70 text-[11px] font-bold uppercase tracking-wider text-slate-500">
            <tr>
              <th className="w-10 px-4 py-3.5 text-center">
                <button
                  type="button"
                  onClick={onToggleSelectAll}
                  aria-label="Select all reports"
                  className="text-slate-400 hover:text-slate-600 cursor-pointer"
                >
                  {isAllSelected ? (
                    <CheckSquare className="h-4 w-4 text-blue-600" />
                  ) : (
                    <Square className="h-4 w-4" />
                  )}
                </button>
              </th>
              <th className="px-4 py-3.5">Severity</th>
              <th className="px-4 py-3.5">Tracking ID</th>
              <th className="px-4 py-3.5 text-center">Photo</th>
              <th className="px-4 py-3.5">Event</th>
              <th className="px-4 py-3.5">Location</th>
              <th className="px-4 py-3.5">Reported</th>
              <th className="px-4 py-3.5">Credibility</th>
              <th className="px-4 py-3.5">Status</th>
              <th className="px-4 py-3.5 text-right">Action</th>
            </tr>
          </thead>

          {/* Table Body */}
          <tbody className="divide-y divide-slate-100">
            {reports.map((report) => {
              const isSelected = selectedIds.has(report.id);
              const isActiveRow = selectedReport?.id === report.id;
              const hasMedia = report.media && report.media.length > 0;
              const mediaUrl = hasMedia ? report.media[0].url : null;

              return (
                <tr
                  key={report.id}
                  onClick={() => onSelectReport(report)}
                  className={`transition-colors cursor-pointer hover:bg-blue-50/40 ${
                    isActiveRow ? 'bg-blue-50/70' : ''
                  }`}
                >
                  {/* Selection Checkbox */}
                  <td
                    className="px-4 py-3 text-center"
                    onClick={(e) => {
                      e.stopPropagation();
                      onToggleSelectId(report.id);
                    }}
                  >
                    <button
                      type="button"
                      aria-label={`Select report ${report.tracking_id}`}
                      className="text-slate-400 hover:text-slate-600 cursor-pointer"
                    >
                      {isSelected ? (
                        <CheckSquare className="h-4 w-4 text-blue-600" />
                      ) : (
                        <Square className="h-4 w-4" />
                      )}
                    </button>
                  </td>

                  {/* Severity */}
                  <td className="px-4 py-3">
                    {getSeverityBadge(report.severity)}
                  </td>

                  {/* Tracking ID */}
                  <td className="px-4 py-3 font-mono font-bold text-slate-900">
                    {report.tracking_id}
                  </td>

                  {/* Photo Thumbnail */}
                  <td className="px-4 py-3 text-center">
                    {mediaUrl ? (
                      <img
                        src={mediaUrl}
                        alt="Evidence thumbnail"
                        className="mx-auto h-9 w-9 rounded-lg object-cover border border-slate-200 shadow-2xs"
                        onError={(e) => {
                          (e.target as HTMLElement).style.display = 'none';
                        }}
                      />
                    ) : (
                      <div className="mx-auto flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100 text-slate-400 border border-slate-200">
                        <ImageOff className="h-4 w-4" />
                      </div>
                    )}
                  </td>

                  {/* Event Category */}
                  <td className="px-4 py-3 font-semibold text-slate-800">
                    {report.category?.title || report.title}
                  </td>

                  {/* Location */}
                  <td className="px-4 py-3 text-slate-700">
                    {report.location?.name || `${report.location?.latitude.toFixed(2)}, ${report.location?.longitude.toFixed(2)}`}
                  </td>

                  {/* Reported Time */}
                  <td className="px-4 py-3 text-slate-600">
                    {formatReportTime(report.occurred_at || report.created_at)}
                  </td>

                  {/* Credibility (Honest Representation) */}
                  <td className="px-4 py-3" title={report.credibility_reason || undefined}>
                    {report.credibility_score > 0 ? (
                      <div className="flex flex-col space-y-0.5">
                        <div className="flex items-center space-x-2">
                          <div className="h-1.5 w-12 rounded-full bg-slate-200 overflow-hidden">
                            <div
                              className="h-full bg-emerald-500"
                              style={{ width: `${Math.round(report.credibility_score * 100)}%` }}
                            />
                          </div>
                          <span className="font-mono text-slate-700 font-bold">
                            {report.credibility_score.toFixed(2)}
                          </span>
                        </div>
                        {report.credibility_reason && (
                          <span className="text-[10px] text-slate-500 font-normal line-clamp-1 max-w-[180px]">
                            {report.credibility_reason}
                          </span>
                        )}
                      </div>
                    ) : (
                      <span className="text-[11px] text-slate-400 italic">
                        Not Calculated
                      </span>
                    )}
                  </td>

                  {/* Status */}
                  <td className="px-4 py-3">
                    {getStatusBadge(report.verification_status)}
                  </td>

                  {/* Action */}
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectReport(report);
                      }}
                      className="inline-flex items-center space-x-1 rounded-lg px-2.5 py-1 text-xs font-bold text-blue-600 hover:bg-blue-100 transition-colors cursor-pointer"
                    >
                      <span>Review</span>
                      <ChevronRight className="h-3.5 w-3.5" />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
