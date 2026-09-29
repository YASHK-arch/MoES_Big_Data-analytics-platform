import React, { useState, useEffect, useCallback } from 'react';
import {
  GeocodedLocation,
  DEFAULT_NATIONAL_LOCATION,
  reverseGeocode,
  calculateBbox,
} from '@/services/nominatimService';
import { LocationContext } from './LocationContextCore';

export const LocationProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [currentLocation, setCurrentLocation] = useState<GeocodedLocation>(DEFAULT_NATIONAL_LOCATION);
  const [isDefault, setIsDefault] = useState<boolean>(true);
  const [isDetecting, setIsDetecting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const detectLocation = useCallback(async () => {
    if (!navigator.geolocation) {
      setError('Geolocation not supported by browser');
      setIsDefault(true);
      return;
    }

    setIsDetecting(true);
    setError(null);

    try {
      const position = await new Promise<GeolocationPosition>((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(resolve, reject, {
          enableHighAccuracy: false,
          timeout: 7000,
          maximumAge: 1000 * 60 * 10, // 10 minutes cache
        });
      });

      const { latitude, longitude } = position.coords;
      const geocoded = await reverseGeocode(latitude, longitude);

      setCurrentLocation(geocoded);
      setIsDefault(false);
      setError(null);
    } catch (err: unknown) {
      const geoErr = err as GeolocationPositionError;
      let errMsg = 'Location access denied';
      if (geoErr?.code === 1) {
        errMsg = 'Location permission denied by user';
      } else if (geoErr?.code === 2) {
        errMsg = 'Location unavailable';
      } else if (geoErr?.code === 3) {
        errMsg = 'Location request timed out';
      }
      console.info('Geolocation notice:', errMsg);
      setError(errMsg);
      setIsDefault(true);
    } finally {
      setIsDetecting(false);
    }
  }, []);

  const setLocation = useCallback((loc: GeocodedLocation) => {
    setCurrentLocation(loc);
    setIsDefault(loc.name === 'All India' || !loc.bbox);
    setError(null);
  }, []);

  const setCoords = useCallback(async (lat: number, lon: number, name?: string) => {
    setIsDetecting(true);
    try {
      if (name) {
        setCurrentLocation({
          name,
          displayName: name,
          lat,
          lon,
          bbox: calculateBbox(lat, lon),
        });
      } else {
        const geocoded = await reverseGeocode(lat, lon);
        setCurrentLocation(geocoded);
      }
      setIsDefault(false);
      setError(null);
    } catch (err) {
      console.warn('Failed to set coordinates:', err);
    } finally {
      setIsDetecting(false);
    }
  }, []);

  const resetToNational = useCallback(() => {
    setCurrentLocation(DEFAULT_NATIONAL_LOCATION);
    setIsDefault(true);
    setError(null);
  }, []);

  // Detect user location on initial application load
  useEffect(() => {
    detectLocation();
  }, [detectLocation]);

  return (
    <LocationContext.Provider
      value={{
        currentLocation,
        isDefault,
        isDetecting,
        error,
        detectLocation,
        setLocation,
        setCoords,
        resetToNational,
      }}
    >
      {children}
    </LocationContext.Provider>
  );
};
