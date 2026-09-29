import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { MapContainer, TileLayer, Marker, Popup, GeoJSON, Circle } from 'react-leaflet';
import L from 'leaflet';
import { Globe, Layers, RefreshCw } from 'lucide-react';
import { Navbar } from '@/components/layout/Navbar';
import { Footer } from '@/components/layout/Footer';
import { routeApi } from '@/services/routeApi';
import { incidentApi } from '@/services/incidentApi';
import { GeoJSONFeatureCollection } from '@/types';

// Custom Leaflet incident marker icon for national view
const nationalIncidentIcon = (severity: string) => {
  const bg = severity === 'SEVERE' ? 'bg-rose-600' : severity === 'HIGH' ? 'bg-orange-500' : 'bg-blue-600';
  return L.divIcon({
    className: 'national-incident-marker',
    html: `<div class="flex h-5 w-5 items-center justify-center rounded-full ${bg} text-white font-extrabold text-[9px] shadow-md border border-white">
            !
          </div>`,
    iconSize: [20, 20],
    iconAnchor: [10, 10],
  });
};

export const NationalMapPage: React.FC = () => {
  const [showEEZ, setShowEEZ] = useState(true);
  const [showIncidents, setShowIncidents] = useState(true);
  const [showForecasts, setShowForecasts] = useState(true);
  const [showHeatmap, setShowHeatmap] = useState(false);

  // 1. Fetch Nationwide Verified Incidents
  const { data: incidentsGeo, isLoading: isLoadingIncidents, refetch: refetchIncidents } = useQuery<GeoJSONFeatureCollection>({
    queryKey: ['nationalIncidentsGeo'],
    queryFn: () => incidentApi.getGeoIncidents(undefined, { status: 'VERIFIED', hours_ago: 72 }),
    staleTime: 1000 * 60 * 2,
  });

  // 2. Fetch Forecast Advisories & Cyclone Tracks
  const { data: forecastGeo } = useQuery<GeoJSONFeatureCollection>({
    queryKey: ['forecastAdvisoriesGeo'],
    queryFn: () => routeApi.getForecastAdvisories(undefined, true),
    staleTime: 1000 * 60 * 5,
  });

  // 3. Fetch Static EEZ Boundary GeoJSON
  const { data: eezGeo } = useQuery<GeoJSONFeatureCollection>({
    queryKey: ['eezBoundaryGeo'],
    queryFn: async () => {
      const res = await fetch('/static/eez_india_boundary.geojson');
      return res.json();
    },
    staleTime: Infinity,
  });

  const incidentFeatures = incidentsGeo?.features || [];
  const forecastFeatures = forecastGeo?.features || [];

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 font-sans text-slate-900 antialiased">
      <Navbar />

      <main className="flex-1 py-6">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 space-y-6">
          {/* Header */}
          <div className="flex items-center justify-between gap-4 flex-wrap rounded-2xl border border-slate-200 bg-white p-5 sm:p-6 shadow-2xs">
            <div className="flex items-center space-x-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-600 text-white shadow-md">
                <Globe className="h-6 w-6" />
              </div>
              <div>
                <div className="flex items-center space-x-2">
                  <h1 className="text-xl sm:text-2xl font-extrabold text-slate-900 tracking-tight">
                    National Weather & Maritime Map
                  </h1>
                  <span className="rounded-full bg-indigo-100 px-2.5 py-0.5 text-[10px] font-extrabold text-indigo-800 uppercase tracking-wider">
                    All-India + EEZ Scope
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-0.5">
                  Unified operational view combining real-time verified incidents, IMD/NDMA cyclone track advisories, hazard density heatmaps, and India Exclusive Economic Zone boundaries.
                </p>
              </div>
            </div>

            <div className="flex items-center space-x-2">
              <button
                type="button"
                onClick={() => refetchIncidents()}
                className="flex items-center space-x-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-indigo-700 transition-colors cursor-pointer"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${isLoadingIncidents ? 'animate-spin' : ''}`} />
                <span>Refresh National View</span>
              </button>
            </div>
          </div>

          {/* Layer Control Bar */}
          <div className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white p-4 shadow-2xs flex-wrap gap-3">
            <div className="flex items-center space-x-2 text-xs font-bold text-slate-700">
              <Layers className="h-4 w-4 text-indigo-600" />
              <span>Map Layer Toggles:</span>
            </div>

            <div className="flex items-center space-x-4 text-xs font-semibold text-slate-700 flex-wrap gap-y-2">
              {/* Toggle Incidents */}
              <label className="flex items-center space-x-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={showIncidents}
                  onChange={(e) => setShowIncidents(e.target.checked)}
                  className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 h-4 w-4 cursor-pointer"
                />
                <span className="flex items-center space-x-1">
                  <span className="h-2.5 w-2.5 rounded-full bg-blue-600" />
                  <span>Verified Incidents ({incidentFeatures.length})</span>
                </span>
              </label>

              {/* Toggle Forecast Advisories */}
              <label className="flex items-center space-x-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={showForecasts}
                  onChange={(e) => setShowForecasts(e.target.checked)}
                  className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 h-4 w-4 cursor-pointer"
                />
                <span className="flex items-center space-x-1">
                  <span className="h-2.5 w-2.5 rounded-full bg-indigo-600" />
                  <span>IMD/NDMA Forecast Advisories ({forecastFeatures.length})</span>
                </span>
              </label>

              {/* Toggle Hazard Heatmap */}
              <label className="flex items-center space-x-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={showHeatmap}
                  onChange={(e) => setShowHeatmap(e.target.checked)}
                  className="rounded border-slate-300 text-rose-600 focus:ring-rose-500 h-4 w-4 cursor-pointer"
                />
                <span className="flex items-center space-x-1">
                  <span className="h-2.5 w-2.5 rounded-full bg-rose-500 animate-pulse" />
                  <span>Hazard Density Heatmap (B5)</span>
                </span>
              </label>

              {/* Toggle EEZ Boundary */}
              <label className="flex items-center space-x-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={showEEZ}
                  onChange={(e) => setShowEEZ(e.target.checked)}
                  className="rounded border-slate-300 text-cyan-600 focus:ring-cyan-500 h-4 w-4 cursor-pointer"
                />
                <span className="flex items-center space-x-1">
                  <span className="h-2.5 w-2.5 rounded-full bg-cyan-500" />
                  <span>India EEZ Maritime Boundary</span>
                </span>
              </label>
            </div>
          </div>

          {/* Map Container */}
          <div className="relative h-[620px] w-full rounded-2xl overflow-hidden border border-slate-200 shadow-sm bg-slate-900">
            <MapContainer
              center={[20.5937, 78.9629]} // All-India centroid
              zoom={5}
              scrollWheelZoom={true}
              className="h-full w-full"
            >
              <TileLayer
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              />

              {/* EEZ GeoJSON Layer */}
              {showEEZ && eezGeo && (
                <GeoJSON
                  data={eezGeo as unknown as GeoJSON.GeoJsonObject}
                  style={{
                    color: '#06b6d4',
                    fillColor: '#0891b2',
                    fillOpacity: 0.05,
                    weight: 2,
                    dashArray: '6 6',
                  }}
                />
              )}

              {/* Forecast Advisories GeoJSON Layer */}
              {showForecasts && forecastFeatures.length > 0 && (
                <GeoJSON
                  key={JSON.stringify(forecastGeo)}
                  data={forecastGeo as unknown as GeoJSON.GeoJsonObject}
                  style={{
                    color: '#6366f1',
                    fillColor: '#818cf8',
                    fillOpacity: 0.25,
                    weight: 2.5,
                  }}
                  onEachFeature={(feature, layer) => {
                    const props = feature.properties;
                    layer.bindPopup(`
                      <div class="p-1 text-xs space-y-1">
                        <span class="rounded bg-indigo-100 px-1.5 py-0.5 text-[10px] font-bold text-indigo-800 uppercase">
                          ${props.category_code || 'ADVISORY'}
                        </span>
                        <h4 class="font-bold text-slate-900">${props.title}</h4>
                        <p class="text-slate-600 text-[11px]">${props.location_name || ''}</p>
                        <p class="text-indigo-900 bg-indigo-50 p-1.5 rounded font-medium text-[10px]">
                          ${props.credibility_reason || 'Official Bulletin'}
                        </p>
                      </div>
                    `);
                  }}
                />
              )}

              {/* Hazard Density Heatmap Layer (B5) */}
              {showHeatmap &&
                incidentFeatures.map((feat) => {
                  if (feat.geometry.type !== 'Point') return null;
                  const coords = feat.geometry.coordinates as [number, number];
                  const color = feat.properties.severity === 'SEVERE' ? '#ef4444' : feat.properties.severity === 'HIGH' ? '#f97316' : '#eab308';
                  return (
                    <Circle
                      key={`heat-${feat.properties.id}`}
                      center={[coords[1], coords[0]]}
                      radius={45000} // 45km density radius
                      pathOptions={{
                        color,
                        fillColor: color,
                        fillOpacity: 0.35,
                        weight: 1,
                      }}
                    />
                  );
                })}

              {/* Incident Markers */}
              {showIncidents &&
                incidentFeatures.map((feat) => {
                  if (feat.geometry.type !== 'Point') return null;
                  const coords = feat.geometry.coordinates as [number, number];
                  return (
                    <Marker
                      key={feat.properties.id}
                      position={[coords[1], coords[0]]}
                      icon={nationalIncidentIcon(feat.properties.severity)}
                    >
                      <Popup>
                        <div className="p-1 space-y-1 text-xs">
                          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-bold text-slate-700 uppercase">
                            {feat.properties.category_code}
                          </span>
                          <h4 className="font-bold text-slate-900">{feat.properties.title}</h4>
                          <p className="text-slate-500 text-[11px]">{feat.properties.location_name || 'India Area'}</p>
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
            </MapContainer>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
};
