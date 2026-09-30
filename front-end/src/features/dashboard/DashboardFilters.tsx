import React from 'react';
import { Filter, RefreshCw, Clock, AlertTriangle, MapPin, CheckCircle } from 'lucide-react';
import { REGIONS, HAZARDS, STATUSES } from './constants';

export type TimeRangeOption = '24h' | '48h' | '7d' | 'all';

export interface DashboardFilterState {
  timeRange: TimeRangeOption;
  hazard: string;
  region: string;
  status: string;
  hideDemo?: boolean;
}

interface DashboardFiltersProps {
  filters: DashboardFilterState;
  onChange: (newFilters: DashboardFilterState) => void;
  onRefresh: () => void;
  isFetching: boolean;
}

export const DashboardFilters: React.FC<DashboardFiltersProps> = ({
  filters,
  onChange,
  onRefresh,
  isFetching,
}) => {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        {/* Left: Filter dropdowns group */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center space-x-2 text-slate-700 font-semibold text-sm mr-1">
            <Filter className="h-4 w-4 text-blue-600" />
            <span>Filters:</span>
          </div>

          {/* Time Range Filter */}
          <div className="relative">
            <select
              value={filters.timeRange}
              onChange={(e) =>
                onChange({ ...filters, timeRange: e.target.value as TimeRangeOption })
              }
              aria-label="Filter by time range"
              className="appearance-none rounded-xl border border-slate-200 bg-slate-50/70 py-2 pl-8 pr-8 text-xs font-semibold text-slate-700 hover:border-slate-300 focus:border-blue-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition-colors"
            >
              <option value="24h">Last 24 Hours</option>
              <option value="48h">Last 48 Hours</option>
              <option value="7d">Last 7 Days</option>
              <option value="all">All Time</option>
            </select>
            <Clock className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-400" />
          </div>

          {/* Hazard / Category Filter */}
          <div className="relative">
            <select
              value={filters.hazard}
              onChange={(e) => onChange({ ...filters, hazard: e.target.value })}
              aria-label="Filter by hazard event type"
              className="appearance-none rounded-xl border border-slate-200 bg-slate-50/70 py-2 pl-8 pr-8 text-xs font-semibold text-slate-700 hover:border-slate-300 focus:border-blue-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition-colors"
            >
              {HAZARDS.map((h) => (
                <option key={h.code} value={h.code}>
                  {h.label}
                </option>
              ))}
            </select>
            <AlertTriangle className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-400" />
          </div>

          {/* Geographic Region Filter */}
          <div className="relative">
            <select
              value={filters.region}
              onChange={(e) => onChange({ ...filters, region: e.target.value })}
              aria-label="Filter by geographic region"
              className="appearance-none rounded-xl border border-slate-200 bg-slate-50/70 py-2 pl-8 pr-8 text-xs font-semibold text-slate-700 hover:border-slate-300 focus:border-blue-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition-colors"
            >
              {Object.entries(REGIONS).map(([code, reg]) => (
                <option key={code} value={code}>
                  {reg.label}
                </option>
              ))}
            </select>
            <MapPin className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-400" />
          </div>

          {/* Verification Status Filter */}
          <div className="relative">
            <select
              value={filters.status}
              onChange={(e) => onChange({ ...filters, status: e.target.value })}
              aria-label="Filter by verification status"
              className="appearance-none rounded-xl border border-slate-200 bg-slate-50/70 py-2 pl-8 pr-8 text-xs font-semibold text-slate-700 hover:border-slate-300 focus:border-blue-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition-colors"
            >
              {STATUSES.map((s) => (
                <option key={s.code} value={s.code}>
                  {s.label}
                </option>
              ))}
            </select>
            <CheckCircle className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-400" />
          </div>
        </div>

        {/* Right: Toggle & Refresh Data Button */}
        <div className="flex items-center justify-end space-x-3">
          <label className="flex items-center space-x-2 text-xs font-semibold text-slate-700 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={Boolean(filters.hideDemo)}
              onChange={(e) => onChange({ ...filters, hideDemo: e.target.checked })}
              className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 h-4 w-4"
              data-testid="hide-demo-toggle"
            />
            <span>Hide Demo Data</span>
          </label>

          <button
            type="button"
            onClick={onRefresh}
            disabled={isFetching}
            className="flex items-center space-x-2 rounded-xl bg-blue-600 px-4 py-2 text-xs font-bold text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-600/30 disabled:opacity-70 transition-all cursor-pointer"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? 'animate-spin' : ''}`} />
            <span>Refresh Data</span>
          </button>
        </div>
      </div>
    </div>
  );
};
