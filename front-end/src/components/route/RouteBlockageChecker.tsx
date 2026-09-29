import React, { useState } from 'react';
import { Navigation, Search, AlertTriangle, ShieldCheck, MapPin, X } from 'lucide-react';
import { useLocationScope } from '@/hooks/useLocationScope';
import { searchLocations, GeocodedLocation } from '@/services/nominatimService';
import { routeApi, RouteCheckResponseData } from '@/services/routeApi';

import { INDIA_CENTROID } from '@/constants/geo';

interface RouteBlockageCheckerProps {
  onRouteChecked: (data: RouteCheckResponseData | null) => void;
}

export const RouteBlockageChecker: React.FC<RouteBlockageCheckerProps> = ({ onRouteChecked }) => {
  const { currentLocation } = useLocationScope();

  const [destQuery, setDestQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<GeocodedLocation[]>([]);
  const [selectedDest, setSelectedDest] = useState<GeocodedLocation | null>(null);

  const [isChecking, setIsChecking] = useState(false);
  const [routeResult, setRouteResult] = useState<RouteCheckResponseData | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleSearchInput = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setDestQuery(val);
    setSelectedDest(null);

    if (val.trim().length < 3) {
      setSearchResults([]);
      return;
    }

    setIsSearching(true);
    try {
      const results = await searchLocations(val);
      setSearchResults(results);
    } catch {
      setSearchResults([]);
    } finally {
      setIsSearching(false);
    }
  };

  const handleSelectDest = (dest: GeocodedLocation) => {
    setSelectedDest(dest);
    setDestQuery(dest.name);
    setSearchResults([]);
  };

  const handleRunRouteCheck = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();

    if (!selectedDest) {
      setErrorMsg('Please select a destination from the location search dropdown.');
      return;
    }

    const origLat = currentLocation.lat || INDIA_CENTROID[0];
    const origLng = currentLocation.lon || INDIA_CENTROID[1];

    setIsChecking(true);
    setErrorMsg(null);

    try {
      const res = await routeApi.checkRoute({
        origin: { latitude: origLat, longitude: origLng, name: currentLocation.name },
        destination: { latitude: selectedDest.lat, longitude: selectedDest.lon, name: selectedDest.displayName },
        corridor_km: 2.0,
      });

      if (res.success && res.data) {
        setRouteResult(res.data);
        onRouteChecked(res.data);
      } else {
        setErrorMsg('Unable to perform route blockage check.');
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Error executing route safety corridor check.');
    } finally {
      setIsChecking(false);
    }
  };

  const handleClearRoute = () => {
    setDestQuery('');
    setSelectedDest(null);
    setRouteResult(null);
    setErrorMsg(null);
    onRouteChecked(null);
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-blue-50 text-blue-600">
            <Navigation className="h-4 w-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-900">Destination Hazard & Corridor Check</h3>
            <p className="text-[11px] text-slate-400">
              Check if active flood, cyclone, or storm hazards intersect your travel route corridor (2 km buffer).
            </p>
          </div>
        </div>

        {routeResult && (
          <button
            type="button"
            onClick={handleClearRoute}
            className="flex items-center space-x-1 text-xs font-bold text-slate-400 hover:text-slate-600"
          >
            <X className="h-3.5 w-3.5" />
            <span>Clear Path</span>
          </button>
        )}
      </div>

      {/* Form Input */}
      <form onSubmit={handleRunRouteCheck} className="relative flex items-center space-x-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-3 h-4 w-4 text-slate-400" />
          <input
            type="text"
            value={destQuery}
            onChange={handleSearchInput}
            placeholder="Enter destination city, landmark, or area..."
            className="w-full rounded-xl border border-slate-200 bg-slate-50/50 py-2.5 pl-9 pr-4 text-xs font-medium text-slate-800 placeholder-slate-400 focus:border-blue-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20"
          />

          {/* Search Dropdown */}
          {isSearching ? (
            <div className="absolute left-0 right-0 top-12 z-20 rounded-xl border border-slate-200 bg-white p-3 text-center text-xs text-slate-400 shadow-lg">
              Searching destination...
            </div>
          ) : searchResults.length > 0 ? (
            <div className="absolute left-0 right-0 top-12 z-20 max-h-48 overflow-y-auto rounded-xl border border-slate-200 bg-white shadow-xl divide-y divide-slate-100">
              {searchResults.map((res, idx) => (
                <button
                  key={`${res.lat}_${res.lon}_${idx}`}
                  type="button"
                  onClick={() => handleSelectDest(res)}
                  className="flex w-full items-start space-x-2.5 p-3 text-left hover:bg-blue-50/60 transition-colors"
                >
                  <MapPin className="h-4 w-4 text-blue-600 shrink-0 mt-0.5" />
                  <div>
                    <p className="text-xs font-bold text-slate-900">{res.name}</p>
                    <p className="text-[11px] text-slate-500 line-clamp-1">{res.displayName}</p>
                  </div>
                </button>
              ))}
            </div>
          ) : null}
        </div>

        <button
          type="submit"
          disabled={isChecking || !selectedDest}
          className="rounded-xl bg-blue-600 px-4 py-2.5 text-xs font-bold text-white shadow-sm hover:bg-blue-700 disabled:opacity-50 transition-all shrink-0 cursor-pointer"
        >
          {isChecking ? 'Checking...' : 'Check Route Safety'}
        </button>
      </form>

      {errorMsg && (
        <p className="text-xs font-medium text-rose-600 bg-rose-50 p-2.5 rounded-xl border border-rose-200">
          {errorMsg}
        </p>
      )}

      {/* Result Status Banner */}
      {routeResult && (
        <div
          className={`rounded-2xl p-4 border text-xs space-y-2 animate-in fade-in duration-300 ${
            routeResult.is_blocked
              ? 'bg-rose-50/90 border-rose-200 text-rose-950'
              : 'bg-emerald-50/90 border-emerald-200 text-emerald-950'
          }`}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              {routeResult.is_blocked ? (
                <AlertTriangle className="h-5 w-5 text-rose-600 shrink-0" />
              ) : (
                <ShieldCheck className="h-5 w-5 text-emerald-600 shrink-0" />
              )}
              <span className="font-extrabold text-sm">
                {routeResult.is_blocked
                  ? `Path May Be Affected — ${routeResult.hazard_count} Hazard(s) Detected!`
                  : 'Path Clear — No Active Hazards Detected'}
              </span>
            </div>
            <span className="font-mono text-[11px] font-bold opacity-75">
              Corridor: {routeResult.corridor_km} km
            </span>
          </div>

          <p className="text-[11px] leading-relaxed opacity-90">
            {routeResult.is_blocked
              ? `Spatial buffer corridor check detected ${routeResult.hazard_count} verified weather hazard(s) intersecting your path line (highest severity: ${routeResult.highest_severity || 'MODERATE'}). Exercise caution.`
              : 'PostGIS corridor check confirms zero verified weather hazards intersecting your origin-to-destination path corridor.'}
          </p>

          {/* Intersecting hazard items */}
          {routeResult.is_blocked && routeResult.intersecting_incidents.length > 0 && (
            <div className="mt-3 space-y-2 pt-2 border-t border-rose-200/60">
              <span className="font-bold text-[11px] uppercase tracking-wider text-rose-900 block">
                Intersecting Hazard Details:
              </span>
              <div className="space-y-1.5 max-h-36 overflow-y-auto">
                {routeResult.intersecting_incidents.map((hz) => (
                  <div
                    key={hz.id}
                    className="flex items-center justify-between rounded-xl bg-white/80 p-2 text-[11px] border border-rose-200/80"
                  >
                    <div>
                      <span className="font-bold text-slate-900">{hz.title}</span>
                      <span className="text-slate-500 block text-[10px]">
                        {hz.location_name || 'Corridor Point'} • Distance to path center: {hz.distance_to_corridor_center_m}m
                      </span>
                    </div>
                    <span className="rounded bg-rose-100 px-1.5 py-0.5 text-[10px] font-extrabold text-rose-800">
                      {hz.severity}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
