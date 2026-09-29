import { createContext } from 'react';
import { GeocodedLocation } from '@/services/nominatimService';

export interface LocationState {
  currentLocation: GeocodedLocation;
  isDefault: boolean;
  isDetecting: boolean;
  error: string | null;
  detectLocation: () => Promise<void>;
  setLocation: (loc: GeocodedLocation) => void;
  setCoords: (lat: number, lon: number, name?: string) => Promise<void>;
  resetToNational: () => void;
}

export const LocationContext = createContext<LocationState | undefined>(undefined);
