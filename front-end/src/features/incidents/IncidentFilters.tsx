// Incident Filter Controls with Automatic Page-Reset

import React from 'react';
import { Search, RotateCcw } from 'lucide-react';

export interface IncidentFilterState {
  searchQuery: string;
  category: string;
  severity: string;
  verification_status: string;
  readiness: string;
  min_credibility?: number;
}

interface IncidentFiltersProps {
  filters: IncidentFilterState;
  onChange: (filters: IncidentFilterState) => void;
  onReset: () => void;
  totalRecords?: number;
}

const CATEGORY_OPTIONS: { value: string; label: string }[] = [
  { value: 'ALL', label: 'All Hazards' },
  { value: 'FLOOD_WATERLOGGING', label: 'Flood / Waterlogging' },
  { value: 'HEAVY_RAINFALL', label: 'Heavy Rainfall' },
  { value: 'CYCLONE_STORM', label: 'Cyclone / Storm' },
  { value: 'URBAN_FLOOD', label: 'Urban Inundation' },
  { value: 'HEATWAVE', label: 'Heatwave' },
  { value: 'HAILSTORM', label: 'Hailstorm' },
  { value: 'LANDSLIDE', label: 'Landslide' },
  { value: 'THUNDERSTORM_LIGHTNING', label: 'Thunderstorm' },
  { value: 'DROUGHT', label: 'Drought' },
  { value: 'FOG', label: 'Dense Fog' },
  { value: 'DUST_STORM', label: 'Dust Storm' },
  { value: 'STRONG_WIND', label: 'Strong Wind' },
  { value: 'OTHER', label: 'Other Event' },
];

const SEVERITY_OPTIONS: { value: string; label: string }[] = [
  { value: 'ALL', label: 'All Severities' },
  { value: 'SEVERE', label: 'Severe' },
  { value: 'HIGH', label: 'High' },
  { value: 'MODERATE', label: 'Moderate' },
  { value: 'LOW', label: 'Low' },
];

const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: 'ALL', label: 'All Statuses' },
  { value: 'PENDING', label: 'Pending Triage' },
  { value: 'UNDER_REVIEW', label: 'Under Review' },
  { value: 'VERIFIED', label: 'Verified' },
  { value: 'REJECTED', label: 'Rejected' },
  { value: 'DUPLICATE', label: 'Duplicate' },
];

const READINESS_OPTIONS: { value: string; label: string }[] = [
  { value: 'ALL', label: 'All Readiness' },
  { value: 'INTELLIGENCE_READY', label: 'Ready (Complete)' },
  { value: 'INTELLIGENCE_PARTIAL', label: 'Partial (Enriching)' },
  { value: 'INTELLIGENCE_PENDING', label: 'Pending Analysis' },
  { value: 'INTELLIGENCE_FAILED', label: 'Incomplete' },
];

export const IncidentFilters: React.FC<IncidentFiltersProps> = ({
  filters,
  onChange,
  onReset,
  totalRecords,
}) => {
  const handleChange = (key: keyof IncidentFilterState, value: string | number | undefined) => {
    onChange({
      ...filters,
      [key]: value,
    });
  };

  const hasActiveFilters =
    filters.searchQuery ||
    filters.category !== 'ALL' ||
    filters.severity !== 'ALL' ||
    filters.verification_status !== 'ALL' ||
    filters.readiness !== 'ALL' ||
    filters.min_credibility !== undefined;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 sm:p-5 shadow-2xs space-y-4">
      {/* Search and Top Stats */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" aria-hidden="true" />
          <input
            type="text"
            value={filters.searchQuery}
            onChange={(e) => handleChange('searchQuery', e.target.value)}
            placeholder="Search by title, location, or tracking ID (RPT-...)"
            className="w-full rounded-xl border border-slate-200 bg-slate-50/50 pl-10 pr-4 py-2 text-xs sm:text-sm text-slate-900 placeholder:text-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all"
            aria-label="Search incident reports"
          />
        </div>

        <div className="flex items-center space-x-2">
          {totalRecords !== undefined && (
            <span className="text-xs font-bold text-slate-500 bg-slate-50 px-3 py-2 rounded-xl border border-slate-200">
              {totalRecords} Found
            </span>
          )}

          {hasActiveFilters && (
            <button
              type="button"
              onClick={onReset}
              className="inline-flex items-center justify-center space-x-1.5 rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2 text-xs font-bold text-slate-700 hover:bg-slate-100 transition-colors"
            >
              <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Reset</span>
            </button>
          )}
        </div>
      </div>

      {/* Filter Selectors Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-3 border-t border-slate-100">
        {/* Category */}
        <div>
          <label className="block text-[10px] font-extrabold uppercase tracking-wider text-slate-400 mb-1">
            Hazard Category
          </label>
          <select
            value={filters.category}
            onChange={(e) => handleChange('category', e.target.value)}
            className="w-full rounded-lg border border-slate-200 bg-slate-50/50 px-2.5 py-1.5 text-xs font-semibold text-slate-800 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            aria-label="Filter by Hazard Category"
          >
            {CATEGORY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {/* Severity */}
        <div>
          <label className="block text-[10px] font-extrabold uppercase tracking-wider text-slate-400 mb-1">
            Severity Level
          </label>
          <select
            value={filters.severity}
            onChange={(e) => handleChange('severity', e.target.value)}
            className="w-full rounded-lg border border-slate-200 bg-slate-50/50 px-2.5 py-1.5 text-xs font-semibold text-slate-800 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            aria-label="Filter by Severity"
          >
            {SEVERITY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {/* Verification Status */}
        <div>
          <label className="block text-[10px] font-extrabold uppercase tracking-wider text-slate-400 mb-1">
            Verification
          </label>
          <select
            value={filters.verification_status}
            onChange={(e) => handleChange('verification_status', e.target.value)}
            className="w-full rounded-lg border border-slate-200 bg-slate-50/50 px-2.5 py-1.5 text-xs font-semibold text-slate-800 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            aria-label="Filter by Verification Status"
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {/* Readiness */}
        <div>
          <label className="block text-[10px] font-extrabold uppercase tracking-wider text-slate-400 mb-1">
            Readiness
          </label>
          <select
            value={filters.readiness}
            onChange={(e) => handleChange('readiness', e.target.value)}
            className="w-full rounded-lg border border-slate-200 bg-slate-50/50 px-2.5 py-1.5 text-xs font-semibold text-slate-800 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            aria-label="Filter by Intelligence Readiness"
          >
            {READINESS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
};
