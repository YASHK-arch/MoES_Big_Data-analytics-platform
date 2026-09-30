import React, { useState } from 'react';
import { Filter, ChevronDown } from 'lucide-react';

export interface MapFilters {
  timeRange: string;
  hazard: string;
  state: string;
  status: string;
  hideDemo?: boolean;
}

interface MapFilterBarProps {
  filters: MapFilters;
  onFilterChange: (newFilters: MapFilters) => void;
}

const TIME_OPTIONS = [
  { label: 'Last 24 Hours', value: '24h' },
  { label: 'Last 48 Hours', value: '48h' },
  { label: 'Past 7 Days', value: '7d' },
];

const HAZARD_OPTIONS = [
  { label: 'All Hazards', value: 'ALL' },
  { label: 'Flooding & Waterlogging', value: 'FLOOD_WATERLOGGING' },
  { label: 'Heavy Rainfall', value: 'HEAVY_RAINFALL' },
  { label: 'Thunderstorm & Lightning', value: 'THUNDERSTORM_LIGHTNING' },
  { label: 'Strong Winds', value: 'STRONG_WIND' },
  { label: 'Heatwave', value: 'HEATWAVE' },
  { label: 'Dense Fog', value: 'FOG' },
  { label: 'Dust Storm', value: 'DUST_STORM' },
  { label: 'Cyclone & Storm', value: 'CYCLONE_STORM' },
  { label: 'Hailstorm', value: 'HAILSTORM' },
  { label: 'Landslide', value: 'LANDSLIDE' },
  { label: 'Urban Inundation', value: 'URBAN_FLOOD' },
  { label: 'Drought Condition', value: 'DROUGHT' },
];

const STATE_OPTIONS = [
  { label: 'All States', value: 'ALL' },
  { label: 'Maharashtra', value: 'MH' },
  { label: 'Tamil Nadu', value: 'TN' },
  { label: 'Delhi NCR', value: 'DL' },
  { label: 'Karnataka', value: 'KA' },
  { label: 'Kerala', value: 'KL' },
  { label: 'Assam', value: 'AS' },
  { label: 'Rajasthan', value: 'RJ' },
];

const STATUS_OPTIONS = [
  { label: 'All Statuses', value: 'ALL' },
  { label: 'Verified', value: 'VERIFIED' },
  { label: 'Under Review', value: 'UNDER_REVIEW' },
  { label: 'Pending', value: 'PENDING' },
];

export const MapFilterBar: React.FC<MapFilterBarProps> = ({ filters, onFilterChange }) => {
  const [mobileFilterOpen, setMobileFilterOpen] = useState(false);

  const handleSelect = (key: keyof MapFilters, value: string) => {
    onFilterChange({ ...filters, [key]: value });
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      {/* Mobile Filter Toggle Button */}
      <div className="md:hidden">
        <button
          type="button"
          onClick={() => setMobileFilterOpen(!mobileFilterOpen)}
          className="flex items-center space-x-1.5 rounded-xl border border-slate-300 bg-white/95 px-3 py-2 text-xs font-semibold text-slate-800 shadow-md backdrop-blur-sm"
        >
          <Filter className="h-3.5 w-3.5 text-blue-600" />
          <span>Filters</span>
          <ChevronDown className={`h-3 w-3 transition-transform ${mobileFilterOpen ? 'rotate-180' : ''}`} />
        </button>
      </div>

      {/* Desktop Filter Pills & Mobile Collapsible */}
      <div
        className={`${
          mobileFilterOpen ? 'flex' : 'hidden'
        } md:flex flex-wrap items-center gap-2 w-full md:w-auto mt-2 md:mt-0`}
      >
        {/* Time Range Filter */}
        <div className="relative">
          <select
            value={filters.timeRange}
            onChange={(e) => handleSelect('timeRange', e.target.value)}
            aria-label="Filter by time range"
            className="appearance-none rounded-xl border border-slate-200 bg-white/95 py-2 pl-3 pr-8 text-xs font-semibold text-slate-800 shadow-md backdrop-blur-sm focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-600/20"
          >
            {TIME_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2.5 text-slate-400">
            <ChevronDown className="h-3 w-3" />
          </div>
        </div>

        {/* Hazard Category Filter */}
        <div className="relative">
          <select
            value={filters.hazard}
            onChange={(e) => handleSelect('hazard', e.target.value)}
            aria-label="Filter by hazard type"
            className="appearance-none rounded-xl border border-slate-200 bg-white/95 py-2 pl-3 pr-8 text-xs font-semibold text-slate-800 shadow-md backdrop-blur-sm focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-600/20"
          >
            {HAZARD_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2.5 text-slate-400">
            <ChevronDown className="h-3 w-3" />
          </div>
        </div>

        {/* State/Region Filter */}
        <div className="relative">
          <select
            value={filters.state}
            onChange={(e) => handleSelect('state', e.target.value)}
            aria-label="Filter by state"
            className="appearance-none rounded-xl border border-slate-200 bg-white/95 py-2 pl-3 pr-8 text-xs font-semibold text-slate-800 shadow-md backdrop-blur-sm focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-600/20"
          >
            {STATE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2.5 text-slate-400">
            <ChevronDown className="h-3 w-3" />
          </div>
        </div>

        {/* Status Filter */}
        <div className="relative">
          <select
            value={filters.status}
            onChange={(e) => handleSelect('status', e.target.value)}
            aria-label="Filter by verification status"
            className="appearance-none rounded-xl border border-slate-200 bg-white/95 py-2 pl-3 pr-8 text-xs font-semibold text-slate-800 shadow-md backdrop-blur-sm focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-600/20"
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2.5 text-slate-400">
            <ChevronDown className="h-3 w-3" />
          </div>
        </div>

        {/* Hide Demo Toggle */}
        <label className="flex items-center space-x-1.5 rounded-xl border border-slate-200 bg-white/95 px-3 py-2 text-xs font-semibold text-slate-800 shadow-md backdrop-blur-sm cursor-pointer select-none">
          <input
            type="checkbox"
            checked={Boolean(filters.hideDemo)}
            onChange={(e) => onFilterChange({ ...filters, hideDemo: e.target.checked })}
            className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 h-3.5 w-3.5"
            data-testid="map-hide-demo-toggle"
          />
          <span>Hide Demo</span>
        </label>
      </div>
    </div>
  );
};
