import React, { useState } from 'react';
import { MapPin, Navigation, Search, CheckCircle2, ShieldAlert } from 'lucide-react';
import { useLocationScope } from '@/hooks/useLocationScope';
import { reverseGeocode, searchLocations, GeocodedLocation } from '@/services/nominatimService';

interface LocationGateModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const POPULAR_CITIES = [
  { name: 'Mumbai', lat: 19.0760, lon: 72.8777, label: 'Mumbai, MH' },
  { name: 'Delhi', lat: 28.6139, lon: 77.2090, label: 'Delhi / NCR' },
  { name: 'Bengaluru', lat: 12.9716, lon: 77.5946, label: 'Bengaluru, KA' },
  { name: 'Chennai', lat: 13.0827, lon: 80.2707, label: 'Chennai, TN' },
  { name: 'Kolkata', lat: 22.5726, lon: 88.3639, label: 'Kolkata, WB' },
  { name: 'Hyderabad', lat: 17.3850, lon: 78.4867, label: 'Hyderabad, TS' },
  { name: 'Pune', lat: 18.5204, lon: 73.8567, label: 'Pune, MH' },
  { name: 'Jaipur', lat: 26.9124, lon: 75.7873, label: 'Jaipur, RJ' },
  { name: 'Ahmedabad', lat: 23.0225, lon: 72.5714, label: 'Ahmedabad, GJ' },
  { name: 'Guwahati', lat: 26.1445, lon: 91.7362, label: 'Guwahati, AS' },
  { name: 'Kochi', lat: 9.9312, lon: 76.2673, label: 'Kochi, KL' },
  { name: 'Bhubaneswar', lat: 20.2961, lon: 85.8245, label: 'Bhubaneswar, OD' },
];

export const LocationGateModal: React.FC<LocationGateModalProps> = ({ isOpen, onClose }) => {
  const { setCoords } = useLocationScope();
  const [isLocating, setIsLocating] = useState(false);
  const [geoError, setGeoError] = useState<string | null>(null);

  // Manual search state
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<GeocodedLocation[]>([]);

  if (!isOpen) return null;

  const handleDetectLocation = () => {
    if (!navigator.geolocation) {
      setGeoError('Geolocation is not supported by your browser. Please search manually below.');
      return;
    }

    setIsLocating(true);
    setGeoError(null);

    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const lat = pos.coords.latitude;
        const lng = pos.coords.longitude;

        try {
          const rev = await reverseGeocode(lat, lng);
          const name = rev?.displayName || `${lat.toFixed(4)}, ${lng.toFixed(4)}`;
          await setCoords(lat, lng, name);
          setIsLocating(false);
          onClose();
        } catch {
          await setCoords(lat, lng, `Location (${lat.toFixed(4)}, ${lng.toFixed(4)})`);
          setIsLocating(false);
          onClose();
        }
      },
      (err) => {
        setIsLocating(false);
        if (err.code === err.PERMISSION_DENIED) {
          setGeoError('Location permission denied in browser. Click the 📍 icon in your address bar to Allow, or pick a city below.');
        } else {
          setGeoError('Unable to detect location. Please select a city below or search manually.');
        }
      },
      { timeout: 10000, enableHighAccuracy: true }
    );
  };

  const handleSearchInput = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setSearchQuery(val);

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

  const handleSelectCity = async (res: GeocodedLocation) => {
    await setCoords(res.lat, res.lon, res.displayName);
    onClose();
  };

  const handleSelectPreset = async (city: typeof POPULAR_CITIES[0]) => {
    await setCoords(city.lat, city.lon, city.label);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs">
      <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl border border-slate-100 animate-in fade-in zoom-in-95 duration-200">
        <div className="flex items-center space-x-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-50 text-blue-600 shadow-2xs">
            <MapPin className="h-6 w-6" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-900">Set Your Location</h2>
            <p className="text-xs text-slate-500">
              Unlock real-time weather hazards, flood alerts, and path safety checks around your area.
            </p>
          </div>
        </div>

        {geoError && (
          <div className="mt-4 flex items-start space-x-2 rounded-xl bg-amber-50 p-3 text-xs text-amber-900 border border-amber-200/80">
            <ShieldAlert className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <p className="font-semibold">{geoError}</p>
              <p className="text-[11px] text-amber-700">
                You can also instantly select one of the popular cities below with 1-click.
              </p>
            </div>
          </div>
        )}

        {/* Primary CTA: Geolocation Detect */}
        <div className="mt-5">
          <button
            type="button"
            onClick={handleDetectLocation}
            disabled={isLocating}
            className="flex w-full items-center justify-center space-x-2 rounded-xl bg-blue-600 py-3 text-sm font-bold text-white shadow-md hover:bg-blue-700 active:scale-[0.99] transition-all disabled:opacity-50 cursor-pointer"
          >
            <Navigation className={`h-4 w-4 ${isLocating ? 'animate-spin' : ''}`} />
            <span>{isLocating ? 'Detecting Location...' : 'Use My Current Location (GPS)'}</span>
          </button>
        </div>

        {/* Quick Popular Cities */}
        <div className="mt-4">
          <p className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2">
            Popular Cities (1-Click Setup)
          </p>
          <div className="flex flex-wrap gap-1.5 max-h-24 overflow-y-auto">
            {POPULAR_CITIES.map((city) => (
              <button
                key={city.name}
                type="button"
                onClick={() => handleSelectPreset(city)}
                className="inline-flex items-center space-x-1 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-700 hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700 transition-colors cursor-pointer"
              >
                <span>📍 {city.name}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="my-4 flex items-center space-x-3 text-xs text-slate-400">
          <div className="h-px flex-1 bg-slate-200" />
          <span className="font-semibold uppercase tracking-wider">or search manually</span>
          <div className="h-px flex-1 bg-slate-200" />
        </div>

        {/* Manual Autocomplete Search */}
        <div className="relative">
          <div className="relative">
            <Search className="absolute left-3 top-3 h-4 w-4 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={handleSearchInput}
              placeholder="Search Indian city, district, or PIN code..."
              className="w-full rounded-xl border border-slate-200 bg-slate-50/50 py-2.5 pl-9 pr-4 text-xs font-medium text-slate-800 placeholder-slate-400 focus:border-blue-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            />
          </div>

          {/* Autocomplete dropdown */}
          {isSearching ? (
            <div className="mt-2 rounded-xl border border-slate-200 bg-white p-3 text-center text-xs text-slate-400">
              Searching locations...
            </div>
          ) : searchResults.length > 0 ? (
            <div className="mt-2 max-h-48 overflow-y-auto rounded-xl border border-slate-200 bg-white shadow-lg divide-y divide-slate-100">
              {searchResults.map((res, idx) => (
                <button
                  key={`${res.lat}_${res.lon}_${idx}`}
                  type="button"
                  onClick={() => handleSelectCity(res)}
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
          ) : searchQuery.length >= 3 ? (
            <div className="mt-2 rounded-xl border border-slate-200 bg-white p-3 text-center text-xs text-slate-400">
              No matching locations found in India.
            </div>
          ) : null}
        </div>

        {/* Footer info */}
        <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-3 text-[11px] text-slate-400">
          <div className="flex items-center space-x-1">
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
            <span>Strict privacy: location is kept local in your session.</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="font-bold text-slate-500 hover:text-slate-700 cursor-pointer"
          >
            Skip for now
          </button>
        </div>
      </div>
    </div>
  );
};
