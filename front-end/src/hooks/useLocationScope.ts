import { useContext } from 'react';
import { LocationContext, LocationState } from '@/context/LocationContextCore';

export function useLocationScope(): LocationState {
  const context = useContext(LocationContext);
  if (!context) {
    throw new Error('useLocationScope must be used within a LocationProvider');
  }
  return context;
}
