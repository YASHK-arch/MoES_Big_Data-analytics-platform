import React, { useState, useEffect, useRef, useCallback } from 'react';
import { MapPin, Search, Navigation, X, Loader2, Globe } from 'lucide-react';
import { useLocationScope } from '@/hooks';
import { searchCity, GeocodedLocation } from '@/services/nominatimService';

interface CitySearchBarProps {
  className?: string;
  placeholder?: string;
  isCompact?: boolean;
}

export const CitySearchBar: React.FC<CitySearchBarProps> = ({
  className = '',
  placeholder = 'Search city or region (e.g. Bengaluru, Mumbai)...',
  isCompact = false,
}) => {
  const {
    currentLocation,
    isDefault,
    isDetecting,
    detectLocation,
    setLocation,
    resetToNational,
  } = useLocationScope();

  const [query, setQuery] = useState('');
  const [suggestions, setSuggestions] = useState<GeocodedLocation[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Debounced search effect
  useEffect(() => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setSuggestions([]);
      setIsSearching(false);
      return;
    }

    setIsSearching(true);
    debounceTimerRef.current = setTimeout(async () => {
      try {
        const results = await searchCity(trimmed);
        setSuggestions(results);
        setIsOpen(true);
      } catch (err) {
        console.warn('City search failed:', err);
        setSuggestions([]);
      } finally {
        setIsSearching(false);
      }
    }, 380);

    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [query]);

  // Handle outside click to close dropdown
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelectLocation = useCallback(
    (loc: GeocodedLocation) => {
      setLocation(loc);
      setQuery('');
      setIsOpen(false);
    },
    [setLocation]
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (suggestions.length > 0) {
        handleSelectLocation(suggestions[0]);
      }
    } else if (e.key === 'Escape') {
      setIsOpen(false);
    }
  };

  return (
    <div ref={wrapperRef} className={`relative flex items-center ${className}`}>
      {/* Search Input Container */}
      <div className="relative flex w-full items-center">
        <div className="pointer-events-none absolute left-3 flex items-center text-slate-400">
          <Search className="h-4 w-4" />
        </div>

        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => {
            if (suggestions.length > 0) setIsOpen(true);
          }}
          onKeyDown={handleKeyDown}
          placeholder={isCompact ? 'Search city...' : placeholder}
          className="w-full rounded-xl border border-slate-200 bg-slate-50/80 py-1.5 pl-9 pr-20 text-xs text-slate-800 placeholder-slate-400 shadow-2xs hover:border-slate-300 focus:border-blue-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition-all"
          aria-label="Search city or location"
        />

        {/* Right input action buttons */}
        <div className="absolute right-1.5 flex items-center space-x-1">
          {query ? (
            <button
              type="button"
              onClick={() => {
                setQuery('');
                setSuggestions([]);
                setIsOpen(false);
              }}
              className="rounded-lg p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-600"
              title="Clear search"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          ) : null}

          {/* GPS Locate Me Button */}
          <button
            type="button"
            onClick={detectLocation}
            disabled={isDetecting}
            className="flex items-center rounded-lg p-1 text-slate-500 hover:bg-blue-50 hover:text-blue-600 disabled:opacity-50 transition-colors"
            title="Detect my current location"
            aria-label="Use current location"
          >
            {isDetecting ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-600" />
            ) : (
              <Navigation className="h-3.5 w-3.5" />
            )}
          </button>
        </div>
      </div>

      {/* Autocomplete Suggestions Dropdown */}
      {isOpen && (
        <div className="absolute left-0 top-full z-50 mt-1.5 w-full min-w-[280px] max-w-sm rounded-xl border border-slate-200 bg-white p-1.5 shadow-xl animate-in fade-in slide-in-from-top-1 duration-150">
          {isSearching ? (
            <div className="flex items-center space-x-2 px-3 py-2.5 text-xs text-slate-500">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-600" />
              <span>Searching cities...</span>
            </div>
          ) : suggestions.length > 0 ? (
            <div className="space-y-0.5">
              <div className="px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                Matching Cities & Districts
              </div>
              {suggestions.map((loc, idx) => (
                <button
                  key={`${loc.lat}_${loc.lon}_${idx}`}
                  type="button"
                  onClick={() => handleSelectLocation(loc)}
                  className="flex w-full items-start space-x-2 rounded-lg px-2.5 py-2 text-left text-xs text-slate-700 hover:bg-blue-50 hover:text-blue-700 transition-colors"
                >
                  <MapPin className="mt-0.5 h-3.5 w-3.5 shrink-0 text-blue-600" />
                  <div className="flex-1 truncate">
                    <span className="font-semibold">{loc.name}</span>
                    <span className="block truncate text-[11px] text-slate-500">
                      {loc.displayName}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          ) : query.trim().length >= 2 ? (
            <div className="px-3 py-2 text-xs text-slate-500">
              No matching Indian cities found for &quot;{query}&quot;.
            </div>
          ) : null}

          {/* Quick reset to national overview option */}
          <div className="mt-1 border-t border-slate-100 pt-1">
            <button
              type="button"
              onClick={() => {
                resetToNational();
                setQuery('');
                setIsOpen(false);
              }}
              className="flex w-full items-center space-x-2 rounded-lg px-2.5 py-1.5 text-left text-xs font-medium text-slate-600 hover:bg-slate-100 transition-colors"
            >
              <Globe className="h-3.5 w-3.5 text-slate-500" />
              <span>View All India (National Overview)</span>
            </button>
          </div>
        </div>
      )}

      {/* Non-intrusive Active Location Scope Badge (Optional compact pill) */}
      {!isCompact && (
        <div className="hidden xl:flex items-center ml-2.5 shrink-0">
          <div
            className={`inline-flex items-center space-x-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold border ${
              isDefault
                ? 'bg-amber-50/80 border-amber-200 text-amber-800'
                : 'bg-blue-50/80 border-blue-200 text-blue-800'
            }`}
          >
            {isDefault ? (
              <>
                <Globe className="h-3 w-3 text-amber-600" />
                <span>All India (Default)</span>
              </>
            ) : (
              <>
                <MapPin className="h-3 w-3 text-blue-600" />
                <span className="max-w-[120px] truncate">{currentLocation.name}</span>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
