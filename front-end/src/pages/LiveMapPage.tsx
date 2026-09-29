import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Navbar } from '@/components/layout/Navbar';
import { MobileBottomNav } from '@/components/layout/MobileBottomNav';
import { MapHeaderCard } from '@/features/map/MapHeaderCard';
import { MapFilterBar, MapFilters } from '@/features/map/MapFilterBar';
import { MapLegend } from '@/features/map/MapLegend';
import { SelectedIncidentCard } from '@/features/map/SelectedIncidentCard';
import { LiveMapContainer } from '@/features/map/LiveMapContainer';
import { incidentApi } from '@/services/incidentApi';
import { incidentKeys } from '@/lib/queryKeys';
import { geoJSONToMapPoints, MapIncidentPoint } from '@/features/map/adapters';
import { useLocationScope } from '@/hooks';
import { Info, AlertTriangle, Loader2 } from 'lucide-react';

const REGION_BOUNDS: Record<string, { center: [number, number]; zoom: number; bbox?: string }> = {
  ALL: {
    center: [20.5937, 78.9629],
    zoom: 5,
  },
  MH: {
    center: [19.7515, 75.7139],
    zoom: 7,
    bbox: '72.6,15.6,80.9,22.0',
  },
  TN: {
    center: [11.1271, 78.6569],
    zoom: 7,
    bbox: '76.2,8.0,80.3,13.5',
  },
  DL: {
    center: [28.7041, 77.1025],
    zoom: 10,
    bbox: '76.8,28.4,77.4,28.9',
  },
  KA: {
    center: [15.3173, 75.7139],
    zoom: 7,
    bbox: '74.0,11.5,78.6,18.5',
  },
  KL: {
    center: [10.8505, 76.2711],
    zoom: 7,
    bbox: '74.8,8.3,77.4,12.8',
  },
  AS: {
    center: [26.2006, 92.9376],
    zoom: 7,
    bbox: '89.7,24.1,96.0,28.2',
  },
  RJ: {
    center: [27.0238, 74.2179],
    zoom: 6,
    bbox: '69.5,23.0,78.3,30.2',
  },
};

export const LiveMapPage: React.FC = () => {
  const { currentLocation, isDefault } = useLocationScope();

  const [filters, setFilters] = useState<MapFilters>({
    timeRange: '24h',
    hazard: 'ALL',
    state: 'ALL',
    status: 'ALL',
  });

  const [selectedPoint, setSelectedPoint] = useState<MapIncidentPoint | null>(null);

  // Compute hours_ago for GeoJSON query
  const geoHoursAgo = useMemo(() => {
    if (filters.timeRange === '24h') return 24;
    if (filters.timeRange === '48h') return 48;
    if (filters.timeRange === '7d') return 168;
    return undefined; // All-time
  }, [filters.timeRange]);

  // Compute effective bounding box: manual state filter takes precedence; otherwise use detected/searched city bbox
  const activeBbox = useMemo(() => {
    const regionInfo = REGION_BOUNDS[filters.state];
    if (regionInfo?.bbox) {
      return regionInfo.bbox;
    }
    return currentLocation.bbox || undefined;
  }, [filters.state, currentLocation.bbox]);

  const targetRegion = useMemo(() => {
    const reg = REGION_BOUNDS[filters.state];
    if (reg && filters.state !== 'ALL') {
      return reg;
    }
    if (currentLocation.lat != null && currentLocation.lon != null && !isDefault) {
      return { center: [currentLocation.lat, currentLocation.lon] as [number, number], zoom: 11 };
    }
    return reg;
  }, [filters.state, currentLocation, isDefault]);

  const geoParams = useMemo(() => {
    const p: { status?: string; category?: string; hours_ago?: number } = {};
    if (filters.hazard !== 'ALL') p.category = filters.hazard;
    if (filters.status !== 'ALL') p.status = filters.status;
    if (geoHoursAgo) p.hours_ago = geoHoursAgo;
    return p;
  }, [filters.hazard, filters.status, geoHoursAgo]);

  // Fetch GeoJSON map points using canonical incidentKeys.geo
  const {
    data: geoData,
    isLoading: isGeoLoading,
    isError: isGeoError,
    error: geoError,
  } = useQuery({
    queryKey: incidentKeys.geo(activeBbox || '', geoParams as Record<string, unknown>),
    queryFn: ({ signal }) => incidentApi.getGeoIncidents(activeBbox, geoParams, signal),
    staleTime: 1000 * 30, // 30 seconds
    refetchOnWindowFocus: false,
  });

  const mapPoints = useMemo(() => geoJSONToMapPoints(geoData), [geoData]);

  // Lazy detail fetch for rich multimedia & description upon marker selection
  const {
    data: detailResponse,
    isLoading: isDetailLoading,
  } = useQuery({
    queryKey: incidentKeys.detail(selectedPoint?.id || ''),
    queryFn: ({ signal }) => incidentApi.getIncidentDetail(selectedPoint!.id, signal),
    enabled: !!selectedPoint?.id,
    staleTime: 1000 * 60, // 1 minute
  });

  const selectedReport = useMemo(() => {
    if (!selectedPoint) return null;
    if (detailResponse?.data) {
      return detailResponse.data;
    }
    return selectedPoint;
  }, [selectedPoint, detailResponse]);

  // Calculate unique coordinate locations (4-decimal precision)
  const uniqueLocationsCount = useMemo(() => {
    const set = new Set<string>();
    for (const p of mapPoints) {
      if (p.location?.latitude != null && p.location?.longitude != null) {
        set.add(`${p.location.latitude.toFixed(4)}_${p.location.longitude.toFixed(4)}`);
      }
    }
    return set.size;
  }, [mapPoints]);

  // Transparent, truthful status message
  const statusLabel = useMemo(() => {
    if (isGeoLoading) {
      return 'Loading incident reports...';
    }
    if (isGeoError) {
      return geoError instanceof Error ? geoError.message : 'Failed to retrieve live reports';
    }
    const count = mapPoints.length;
    if (count === 0) {
      return '0 Incidents in Selected View';
    }
    return `${count} Incident${count > 1 ? 's' : ''} on Map (${uniqueLocationsCount} Location${uniqueLocationsCount > 1 ? 's' : ''})`;
  }, [isGeoLoading, isGeoError, geoError, mapPoints.length, uniqueLocationsCount]);

  return (
    <div className="relative flex h-screen w-screen flex-col overflow-hidden bg-slate-100 text-slate-900">
      {/* Navigation Header */}
      <Navbar />

      {/* Main Map Viewport */}
      <main className="relative flex-1 w-full overflow-hidden">
        {/* Fullscreen Map Layer */}
        <LiveMapContainer
          reports={mapPoints}
          selectedReport={selectedPoint}
          onSelectReport={(point) => setSelectedPoint(point)}
          targetRegion={targetRegion}
        />

        {/* Floating Top Header & Filter Controls */}
        <div className="absolute top-4 left-4 z-[900] flex flex-col space-y-3 pointer-events-none max-w-[calc(100vw-2rem)] sm:max-w-xl">
          <div className="pointer-events-auto">
            <MapHeaderCard />
          </div>
          <div className="pointer-events-auto">
            <MapFilterBar filters={filters} onFilterChange={setFilters} />
          </div>
        </div>

        {/* Floating Data Status Banner */}
        <div className="absolute top-4 right-4 z-[900] hidden lg:block pointer-events-auto">
          <div className="flex items-center space-x-2 rounded-xl border border-slate-200/80 bg-white/95 px-3 py-2 text-xs font-semibold text-slate-700 shadow-md backdrop-blur-md">
            {isGeoLoading ? (
              <>
                <Loader2 className="h-4 w-4 text-blue-600 animate-spin" />
                <span>{statusLabel}</span>
              </>
            ) : isGeoError ? (
              <>
                <AlertTriangle className="h-4 w-4 text-rose-600" />
                <span className="text-rose-700">{statusLabel}</span>
              </>
            ) : (
              <>
                <Info className="h-4 w-4 text-blue-600 shrink-0" />
                <span>{statusLabel}</span>
              </>
            )}
          </div>
        </div>

        {/* Floating Legend (Bottom Left on Desktop) */}
        <div className="absolute bottom-6 left-4 z-[900] hidden sm:block pointer-events-auto">
          <MapLegend />
        </div>

        {/* Selected Incident Card (Floating Right on Desktop / Bottom Sheet on Mobile) */}
        {selectedReport && (
          <div className="absolute bottom-16 sm:bottom-6 right-4 sm:right-6 z-[1000] pointer-events-auto max-w-[calc(100vw-2rem)] sm:max-w-md">
            <SelectedIncidentCard
              report={selectedReport}
              isLoadingDetail={isDetailLoading}
              onClose={() => setSelectedPoint(null)}
            />
          </div>
        )}
      </main>

      {/* Mobile Bottom Navigation */}
      <MobileBottomNav />
    </div>
  );
};
