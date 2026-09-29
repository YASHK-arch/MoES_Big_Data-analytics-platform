import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { MapContainer, TileLayer, Marker, Popup, Circle, GeoJSON, useMap } from 'react-leaflet';
import L from 'leaflet';
import { ShieldCheck, AlertTriangle, MapPin, Radio, Compass, Navigation, RefreshCw, Layers } from 'lucide-react';
import { Navbar } from '@/components/layout/Navbar';
import { Footer } from '@/components/layout/Footer';
import { useLocationScope } from '@/hooks/useLocationScope';
import { LocationGateModal } from '@/components/location/LocationGateModal';
import { useProximityAlerts } from '@/hooks/useProximityAlerts';
import { RouteBlockageChecker } from '@/components/route/RouteBlockageChecker';
import { EmergencyContactsCard } from '@/components/common/EmergencyContactsCard';
import { routeApi, RouteCheckResponseData } from '@/services/routeApi';
import { apiClient } from '@/services/client';
import { GeoJSONFeatureCollection } from '@/types';

import { useTranslation } from 'react-i18next';

// Dynamic Leaflet Map Center & Zoom Controller
const ProximityMapController: React.FC<{
  center: [number, number];
  radiusKm: number;
  selectedCoords: [number, number] | null;
}> = ({ center, radiusKm, selectedCoords }) => {
  const map = useMap();

  React.useEffect(() => {
    map.invalidateSize();
  }, [map]);

  React.useEffect(() => {
    if (selectedCoords) {
      map.flyTo(selectedCoords, 14, { duration: 0.8 });
    } else {
      const zoom = radiusKm <= 10 ? 13 : radiusKm <= 25 ? 11 : radiusKm <= 50 ? 10 : 8;
      map.flyTo(center, zoom, { duration: 0.8 });
    }
  }, [center, radiusKm, selectedCoords, map]);

  return null;
};

// Custom Leaflet relief center marker icon
const reliefCenterIcon = L.divIcon({
  className: 'relief-center-marker',
  html: `<div class="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-600 text-white font-bold text-xs shadow-lg border-2 border-white">
          🏕️
        </div>`,
  iconSize: [28, 28],
  iconAnchor: [14, 14],
});

// Custom Leaflet marker icons
const userLocationIcon = L.divIcon({
  className: 'user-location-marker',
  html: `<div class="relative flex h-6 w-6 items-center justify-center">
          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
          <span class="relative inline-flex rounded-full h-4 w-4 bg-blue-600 border-2 border-white shadow-md"></span>
        </div>`,
  iconSize: [24, 24],
  iconAnchor: [12, 12],
});

const hazardMarkerIcon = (severity: string) => {
  const colorClass =
    severity === 'SEVERE'
      ? 'bg-rose-600'
      : severity === 'HIGH'
      ? 'bg-orange-500'
      : severity === 'MODERATE'
      ? 'bg-amber-500'
      : 'bg-blue-500';

  return L.divIcon({
    className: 'hazard-marker',
    html: `<div class="flex h-7 w-7 items-center justify-center rounded-full ${colorClass} text-white font-extrabold text-[10px] shadow-lg border-2 border-white ring-2 ring-slate-900/10">
            !
          </div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });
};

export const CitizenDashboardPage: React.FC = () => {
  const { t } = useTranslation();
  const { currentLocation, setCoords, detectLocation, isDetecting } = useLocationScope();
  const [showLocationGate, setShowLocationGate] = useState(false);
  const [radiusKm, setRadiusKm] = useState(25.0);
  const [routeCheckResult, setRouteCheckResult] = useState<RouteCheckResponseData | null>(null);
  const [showReliefCenters, setShowReliefCenters] = useState(true);
  const [selectedIncidentCoords, setSelectedIncidentCoords] = useState<[number, number] | null>(null);

  // If location is national default (All India), default initial view to Bengaluru where active demo records exist
  const isAllIndia = !currentLocation.lat || currentLocation.name === 'All India';
  const userLat = isAllIndia ? 12.9716 : currentLocation.lat;
  const userLng = isAllIndia ? 77.5946 : currentLocation.lon;
  const locationLabel = isAllIndia ? 'Bengaluru (Demo Active)' : currentLocation.name;

  // Query nearby verified incidents
  const { data: nearbyGeo, isLoading, refetch } = useQuery<GeoJSONFeatureCollection>({
    queryKey: ['nearbyIncidents', userLat, userLng, radiusKm],
    queryFn: () => routeApi.getNearbyIncidents(userLat, userLng, radiusKm, 'VERIFIED'),
    staleTime: 1000 * 60, // 1 min
  });

  // Query nearby relief centers & shelters
  const { data: reliefCentersRes } = useQuery<{
    data: Array<{
      id: string;
      name: string;
      center_type: string;
      capacity: number;
      available_capacity: number;
      contact_phone: string;
      latitude: number;
      longitude: number;
      distance_km: number;
    }>;
  }>({
    queryKey: ['nearbyReliefCenters', userLat, userLng, radiusKm],
    queryFn: () => apiClient(`/geo/relief-centers?lat=${userLat}&lng=${userLng}&radius_km=${radiusKm}`),
    staleTime: 1000 * 60 * 5,
  });

  const reliefCenters = reliefCentersRes?.data || [];

  const features = nearbyGeo?.features || [];
  const totalNearby = features.length;

  // Calculate nearest hazard distance
  let minDist: number | null = null;
  let highestSeverity = 'NONE';
  const severityRank: Record<string, number> = { SEVERE: 4, HIGH: 3, MODERATE: 2, LOW: 1 };
  let maxRank = 0;

  features.forEach((feat) => {
    const geom = feat.geometry as { type: string; coordinates?: unknown };
    if (geom && geom.type === 'Point' && Array.isArray(geom.coordinates)) {
      const coords = geom.coordinates as [number, number];
      const dLat = (coords[1] - userLat) * 111.0;
      const dLng = (coords[0] - userLng) * 111.0 * Math.cos((userLat * Math.PI) / 180);
      const dist = Math.sqrt(dLat * dLat + dLng * dLng);
      if (minDist === null || dist < minDist) {
        minDist = dist;
      }
    }
    const r = severityRank[feat.properties.severity] || 1;
    if (r > maxRank) {
      maxRank = r;
      highestSeverity = feat.properties.severity;
    }
  });

  const { activeAlert, dismissAlert } = useProximityAlerts(radiusKm);

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 font-sans text-slate-900 antialiased">
      <Navbar />

      {/* Feature B3: Sleek Non-Intrusive Floating Proximity Alert Toast */}
      {activeAlert && (
        <aside
          role="alert"
          aria-live="assertive"
          className="fixed top-20 right-4 left-4 sm:left-auto sm:w-[480px] z-50 animate-in slide-in-from-top-3 fade-in duration-300 rounded-2xl border border-rose-500/40 bg-rose-600/95 backdrop-blur-md p-4 text-white shadow-2xl flex items-center justify-between gap-3"
        >
          <div className="flex items-center space-x-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/20 text-white font-extrabold text-lg shrink-0">
              ⚡
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="bg-white text-rose-700 text-[10px] font-black uppercase px-2 py-0.5 rounded-md">
                  NEW REALTIME ALERT NEAR YOU
                </span>
                <span className="text-xs opacity-90">{activeAlert.timestamp}</span>
              </div>
              <h3 className="text-sm font-black mt-0.5">{activeAlert.title}</h3>
              <p className="text-xs opacity-95">
                Detected <strong>{activeAlert.distanceKm} km</strong> from your registered location. Exercise caution.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={dismissAlert}
            className="rounded-lg bg-white/20 px-3 py-1.5 text-xs font-bold text-white hover:bg-white/30 transition-colors shrink-0 cursor-pointer"
          >
            Dismiss
          </button>
        </aside>
      )}

      <main className="flex-1 py-6">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 space-y-6">
          {/* Header Banner */}
          <div className="flex items-center justify-between gap-4 flex-wrap rounded-2xl border border-slate-200 bg-white p-5 sm:p-6 shadow-2xs">
            <div className="flex items-center space-x-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-600 text-white shadow-md">
                <Compass className="h-6 w-6" />
              </div>
              <div>
                <div className="flex items-center space-x-2">
                  <h1 className="text-xl sm:text-2xl font-extrabold text-slate-900 tracking-tight">
                    {t('citizen.title', 'My Area Citizen Dashboard')}
                  </h1>
                  <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-[10px] font-extrabold text-emerald-800 uppercase tracking-wider">
                    Verified Public Feed
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-0.5 flex items-center space-x-1">
                  <MapPin className="h-3.5 w-3.5 text-blue-600 shrink-0" />
                  <span>
                    Location: <strong className="text-slate-800 font-bold">{currentLocation.name}</strong> ({userLat.toFixed(4)}, {userLng.toFixed(4)})
                  </span>
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              <button
                type="button"
                onClick={() => setShowReliefCenters(!showReliefCenters)}
                className={`flex items-center space-x-1.5 rounded-xl border px-3 py-2 text-xs font-bold transition-colors cursor-pointer ${
                  showReliefCenters
                    ? 'border-emerald-300 bg-emerald-50 text-emerald-800'
                    : 'border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100'
                }`}
              >
                <Layers className="h-3.5 w-3.5 text-emerald-600" />
                <span>Shelters ({reliefCenters.length})</span>
              </button>

              <button
                type="button"
                onClick={() => setShowLocationGate(true)}
                className="flex items-center space-x-1.5 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-bold text-slate-700 hover:bg-slate-100 transition-colors cursor-pointer"
              >
                <Navigation className="h-3.5 w-3.5 text-blue-600" />
                <span>Change Location</span>
              </button>

              <button
                type="button"
                onClick={() => refetch()}
                className="flex items-center space-x-1.5 rounded-xl bg-blue-600 px-3.5 py-2 text-xs font-bold text-white shadow-xs hover:bg-blue-700 transition-colors cursor-pointer"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
                <span>Refresh Feed</span>
              </button>
            </div>
          </div>

          {/* KPI Strip */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Active Hazards in Radius */}
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs">
              <div className="flex items-center justify-between text-slate-500">
                <span className="text-xs font-bold uppercase tracking-wider">{t('citizen.activeHazards', 'Active Hazards Nearby')}</span>
                <Radio className="h-4 w-4 text-blue-600" />
              </div>
              <div className="mt-2 flex items-baseline space-x-2">
                <span className="text-3xl font-extrabold text-slate-900 tracking-tight">
                  {totalNearby}
                </span>
                <span className="text-xs font-semibold text-slate-400">within {radiusKm} km</span>
              </div>
              <p className="mt-1 text-[11px] text-slate-500 line-clamp-1">
                Verified disaster & weather alerts
              </p>
            </div>

            {/* Nearest Hazard Distance */}
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs">
              <div className="flex items-center justify-between text-slate-500">
                <span className="text-xs font-bold uppercase tracking-wider">{t('citizen.nearestHazard', 'Nearest Incident')}</span>
                <MapPin className="h-4 w-4 text-amber-600" />
              </div>
              <div className="mt-2 flex items-baseline space-x-2">
                <span className="text-3xl font-extrabold text-slate-900 tracking-tight">
                  {minDist !== null ? (minDist as number).toFixed(1) : '—'}
                </span>
                <span className="text-xs font-semibold text-slate-400">
                  {minDist !== null ? 'km away' : 'No hazards'}
                </span>
              </div>
              <p className="mt-1 text-[11px] text-slate-500 line-clamp-1">
                Proximity to nearest active report
              </p>
            </div>

            {/* Highest Severity Nearby */}
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs">
              <div className="flex items-center justify-between text-slate-500">
                <span className="text-xs font-bold uppercase tracking-wider">Peak Severity Level</span>
                <AlertTriangle className="h-4 w-4 text-rose-600" />
              </div>
              <div className="mt-2 flex items-baseline space-x-2">
                <span className={`text-2xl font-extrabold tracking-tight ${
                  highestSeverity === 'SEVERE' ? 'text-rose-600' : highestSeverity === 'HIGH' ? 'text-orange-600' : 'text-slate-900'
                }`}>
                  {highestSeverity}
                </span>
              </div>
              <p className="mt-1 text-[11px] text-slate-500 line-clamp-1">
                Highest risk level in your area
              </p>
            </div>

            {/* Public Safety Status */}
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs">
              <div className="flex items-center justify-between text-slate-500">
                <span className="text-xs font-bold uppercase tracking-wider">Area Status</span>
                <ShieldCheck className="h-4 w-4 text-emerald-600" />
              </div>
              <div className="mt-2 flex items-center space-x-1.5">
                <span className={`text-xl font-extrabold ${totalNearby > 0 ? 'text-amber-600' : 'text-emerald-600'}`}>
                  {totalNearby > 0 ? 'Advisory Active' : 'Normal / Safe'}
                </span>
              </div>
              <p className="mt-1 text-[11px] text-slate-500 line-clamp-1">
                Filtered strictly to verified reports
              </p>
            </div>
          </div>

          {/* Feature B7: Emergency Helplines Quick-Dial Directory */}
          <EmergencyContactsCard />

          {/* Route Blockage Checker Component */}
          <RouteBlockageChecker onRouteChecked={(data) => setRouteCheckResult(data)} />

          {/* Map & List Layout */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            {/* Main Interactive Proximity Map */}
            <div className="lg:col-span-8 rounded-2xl border border-slate-200 bg-white p-4 shadow-2xs space-y-3">
              {/* Quick Location Scope Bar */}
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-slate-50 p-2.5 border border-slate-200 text-xs">
                <div className="flex items-center space-x-2 text-slate-700">
                  <MapPin className="h-4 w-4 text-blue-600 shrink-0" />
                  <span>Area: <strong className="text-slate-900">{locationLabel}</strong></span>
                </div>

                <div className="flex flex-wrap items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => detectLocation()}
                    disabled={isDetecting}
                    className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-bold text-[11px] transition-colors cursor-pointer disabled:opacity-50"
                  >
                    <Navigation className={`h-3 w-3 ${isDetecting ? 'animate-spin' : ''}`} />
                    <span>{isDetecting ? 'Detecting...' : 'Detect GPS'}</span>
                  </button>

                  <div className="flex items-center space-x-1 bg-white p-0.5 rounded-lg border border-slate-200">
                    <span className="text-[10px] font-bold text-slate-400 px-1.5">Preset:</span>
                    {[
                      { name: 'Bengaluru', lat: 12.9716, lon: 77.5946 },
                      { name: 'Mumbai', lat: 19.0760, lon: 72.8777 },
                      { name: 'Delhi', lat: 28.6139, lon: 77.2090 },
                      { name: 'Chennai', lat: 13.0827, lon: 80.2707 },
                    ].map((city) => (
                      <button
                        key={city.name}
                        type="button"
                        onClick={() => {
                          setSelectedIncidentCoords(null);
                          setCoords(city.lat, city.lon, city.name);
                        }}
                        className={`px-2 py-0.5 rounded-md text-[11px] font-bold transition-all cursor-pointer ${
                          locationLabel.toLowerCase().includes(city.name.toLowerCase())
                            ? 'bg-blue-600 text-white'
                            : 'text-slate-600 hover:bg-slate-100'
                        }`}
                      >
                        {city.name}
                      </button>
                    ))}
                  </div>

                  <button
                    type="button"
                    onClick={() => setShowLocationGate(true)}
                    className="px-2.5 py-1 rounded-lg bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 font-bold text-[11px] transition-colors cursor-pointer"
                  >
                    Search City
                  </button>
                </div>
              </div>

              <div className="flex items-center justify-between">
                <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-500 flex items-center space-x-1.5">
                  <MapPin className="h-4 w-4 text-blue-600" />
                  <span>Proximity Map ({radiusKm} km Radius)</span>
                </h3>

                {/* Radius selector buttons */}
                <div className="flex items-center space-x-1 text-xs font-bold">
                  <span className="text-slate-400 mr-1 text-[11px]">Radius:</span>
                  {[10, 25, 50, 100].map((r) => (
                    <button
                      key={r}
                      type="button"
                      onClick={() => {
                        setSelectedIncidentCoords(null);
                        setRadiusKm(r);
                      }}
                      className={`rounded-lg px-2.5 py-1 transition-colors cursor-pointer ${
                        radiusKm === r ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                      }`}
                    >
                      {r}km
                    </button>
                  ))}
                </div>
              </div>

              <div className="relative h-[340px] sm:h-[400px] lg:h-[480px] w-full rounded-xl overflow-hidden border border-slate-200">
                <MapContainer
                  center={[userLat, userLng]}
                  zoom={11}
                  scrollWheelZoom={true}
                  className="h-full w-full"
                >
                  <ProximityMapController
                    center={[userLat, userLng]}
                    radiusKm={radiusKm}
                    selectedCoords={selectedIncidentCoords}
                  />

                  <TileLayer
                    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                  />

                  {/* Citizen location marker */}
                  <Marker position={[userLat, userLng]} icon={userLocationIcon}>
                    <Popup>
                      <div className="p-1 text-xs">
                        <strong className="font-bold text-blue-900">Your Location</strong>
                        <p className="text-slate-600 mt-0.5">{locationLabel}</p>
                      </div>
                    </Popup>
                  </Marker>

                  {/* Proximity Circle */}
                  <Circle
                    center={[userLat, userLng]}
                    radius={radiusKm * 1000}
                    pathOptions={{ color: '#2563eb', fillColor: '#3b82f6', fillOpacity: 0.08, weight: 1.5, dashArray: '4 4' }}
                  />

                  {/* Hazard markers */}
                  {features.map((feat) => {
                    if (feat.geometry.type !== 'Point') return null;
                    const coords = feat.geometry.coordinates as [number, number];
                    return (
                      <Marker
                        key={feat.properties.id}
                        position={[coords[1], coords[0]]}
                        icon={hazardMarkerIcon(feat.properties.severity)}
                      >
                        <Popup>
                          <div className="p-1 space-y-1 text-xs">
                            <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-extrabold text-slate-700 uppercase">
                              {feat.properties.category_code}
                            </span>
                            <h4 className="font-bold text-slate-900">{feat.properties.title}</h4>
                            <p className="text-slate-500 text-[11px]">{feat.properties.location_name || 'Nearby Area'}</p>
                            {feat.properties.credibility_reason && (
                              <p className="text-blue-900 bg-blue-50 p-1.5 rounded font-medium text-[10px]">
                                {feat.properties.credibility_reason}
                              </p>
                            )}
                          </div>
                        </Popup>
                      </Marker>
                    );
                  })}

                  {/* Feature B1: Relief center & evacuation shelter markers */}
                  {showReliefCenters &&
                    reliefCenters.map((rc) => (
                      <Marker
                        key={rc.id}
                        position={[rc.latitude, rc.longitude]}
                        icon={reliefCenterIcon}
                      >
                        <Popup>
                          <div className="p-1 space-y-1 text-xs">
                            <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-extrabold text-emerald-800 uppercase">
                              {rc.center_type}
                            </span>
                            <h4 className="font-bold text-slate-900">{rc.name}</h4>
                            <p className="text-slate-500 text-[11px]">
                              Capacity: <strong>{rc.available_capacity}</strong> available / {rc.capacity} total
                            </p>
                            {rc.contact_phone && (
                              <p className="font-mono text-blue-700 font-bold text-[11px]">
                                📞 {rc.contact_phone}
                              </p>
                            )}
                          </div>
                        </Popup>
                      </Marker>
                    ))}

                  {/* Route corridor GeoJSON overlay */}
                  {routeCheckResult && routeCheckResult.path_geojson && (
                    <GeoJSON
                      key={JSON.stringify(routeCheckResult.path_geojson)}
                      data={routeCheckResult.path_geojson as unknown as GeoJSON.GeoJsonObject}
                      style={(feature) => {
                        if (feature?.properties?.type === 'CORRIDOR_BUFFER') {
                          return {
                            color: routeCheckResult.is_blocked ? '#e11d48' : '#10b981',
                            fillColor: routeCheckResult.is_blocked ? '#f43f5e' : '#34d399',
                            fillOpacity: 0.2,
                            weight: 2,
                            dashArray: '5 5',
                          };
                        }
                        return {
                          color: routeCheckResult.is_blocked ? '#be123c' : '#059669',
                          weight: 4,
                        };
                      }}
                    />
                  )}
                </MapContainer>
              </div>
            </div>

            {/* Sidebar Nearby Hazards List */}
            <div className="lg:col-span-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs space-y-4">
              <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-500">
                Verified Nearby Incidents ({totalNearby})
              </h3>

              {isLoading ? (
                <div className="space-y-3">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="h-20 rounded-xl bg-slate-100 animate-pulse" />
                  ))}
                </div>
              ) : features.length === 0 ? (
                <div className="py-12 text-center text-slate-400 space-y-2">
                  <ShieldCheck className="h-8 w-8 text-emerald-500 mx-auto" />
                  <p className="text-xs font-semibold text-slate-700">No verified hazards in this radius.</p>
                  <p className="text-[11px] text-slate-400">Try expanding the radius to 50 km or 100 km, or select another city above.</p>
                </div>
              ) : (
                <div className="space-y-3 max-h-[440px] overflow-y-auto pr-1">
                  {features.map((feat) => {
                    const geom = feat.geometry as { type: string; coordinates?: [number, number] };
                    const coords = geom.coordinates;
                    return (
                      <div
                        key={feat.properties.id}
                        onClick={() => {
                          if (coords && coords.length >= 2) {
                            setSelectedIncidentCoords([coords[1], coords[0]]);
                          }
                        }}
                        className="rounded-xl border border-slate-200/80 bg-white p-3.5 shadow-2xs hover:border-blue-400 hover:shadow-xs transition-all space-y-1.5 cursor-pointer group"
                      >
                        <div className="flex items-center justify-between text-[10px]">
                          <span className="font-extrabold text-blue-700 uppercase tracking-wider">
                            {feat.properties.category_code}
                          </span>
                          <span className="rounded bg-rose-100 px-1.5 py-0.2 font-extrabold text-rose-800">
                            {feat.properties.severity}
                          </span>
                        </div>

                        <h4 className="text-xs font-bold text-slate-900 line-clamp-1 group-hover:text-blue-600 transition-colors">
                          {feat.properties.title}
                        </h4>

                        <p className="text-[11px] text-slate-500 flex items-center space-x-1">
                          <MapPin className="h-3 w-3 text-slate-400 shrink-0" />
                          <span className="line-clamp-1">{feat.properties.location_name || 'Nearby Area'}</span>
                        </p>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      </main>

      <Footer />

      {/* Location Gate Onboarding Modal */}
      <LocationGateModal isOpen={showLocationGate} onClose={() => setShowLocationGate(false)} />
    </div>
  );
};
