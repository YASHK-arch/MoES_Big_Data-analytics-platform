// Incident Detail Page — Public & Operational Intelligence View

import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowLeft,
  MapPin,
  Clock,
  ImageOff,
} from 'lucide-react';
import { MapContainer, TileLayer, Marker } from 'react-leaflet';
import L from 'leaflet';
import { Navbar } from '@/components/layout/Navbar';
import { Footer } from '@/components/layout/Footer';
import { FeedbackWidget } from '@/components/incident/FeedbackWidget';
import { CredibilitySection } from '@/features/incidents/CredibilitySection';
import { IntelligenceStatusSection } from '@/features/incidents/IntelligenceStatusSection';
import { LinkedEvidenceSection } from '@/features/incidents/LinkedEvidenceSection';
import { PhysicalObservationsSection } from '@/features/incidents/PhysicalObservationsSection';
import { DuplicateClusterSection } from '@/features/incidents/DuplicateClusterSection';
import { LoadingSkeleton } from '@/components/common/LoadingSkeleton';
import { ErrorCard } from '@/components/common/ErrorCard';
import { incidentApi } from '@/services/incidentApi';
import { incidentKeys } from '@/lib/queryKeys';
import {
  formatDateTime,
  formatHazardCategory,
  formatSeverityBadge,
  formatVerificationStatus,
  formatReadiness,
} from '@/lib/presentation';

const miniMarkerIcon = L.divIcon({
  className: 'custom-mini-marker',
  html: `<div style="
    width: 22px;
    height: 22px;
    background-color: #2563eb;
    border: 3px solid #ffffff;
    border-radius: 50%;
    box-shadow: 0 2px 8px rgba(0,0,0,0.35);
  "></div>`,
  iconSize: [22, 22],
  iconAnchor: [11, 11],
});

export const IncidentDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [mediaErrorMap, setMediaErrorMap] = useState<Record<string, boolean>>({});

  const cleanId = (id || '').trim();

  const { data: response, isLoading, isError, error, refetch } = useQuery({
    queryKey: incidentKeys.detail(cleanId),
    queryFn: ({ signal }) => incidentApi.getIncidentDetail(cleanId, signal),
    enabled: Boolean(cleanId),
    staleTime: 1000 * 30, // 30 seconds
  });

  const incident = response?.data;

  if (!cleanId) {
    return (
      <div className="min-h-screen flex flex-col bg-slate-50">
        <Navbar />
        <main className="flex-1 max-w-4xl mx-auto p-6 flex items-center justify-center">
          <ErrorCard title="Missing Incident Identifier" message="No valid incident ID was provided in the URL." />
        </main>
        <Footer />
      </div>
    );
  }

  const severityStyle = incident ? formatSeverityBadge(incident.severity) : null;
  const verificationStyle = incident ? formatVerificationStatus(incident.verification?.status) : null;
  const readinessStyle = incident ? formatReadiness(incident.intelligence_status?.overall_readiness) : null;

  const hasCoords =
    incident?.location?.latitude != null &&
    incident?.location?.longitude != null &&
    !isNaN(incident.location.latitude) &&
    !isNaN(incident.location.longitude);

  return (
    <div className="flex min-h-screen flex-col bg-slate-50/50 text-slate-900">
      <Navbar />

      <main className="flex-1 py-6 sm:py-10">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 space-y-6">
          {/* Breadcrumb & Navigation */}
          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={() => navigate(-1)}
              className="inline-flex items-center space-x-1.5 text-xs font-bold text-slate-600 hover:text-slate-900 transition-colors"
            >
              <ArrowLeft className="h-4 w-4" aria-hidden="true" />
              <span>Back to Incidents</span>
            </button>

            {incident && (
              <span className="font-mono text-xs text-slate-500 font-bold bg-white px-2.5 py-1 rounded-lg border border-slate-200 shadow-2xs">
                {incident.tracking_id}
              </span>
            )}
          </div>

          {isLoading ? (
            <div className="space-y-6">
              <LoadingSkeleton count={1} className="h-32" />
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                <div className="lg:col-span-7 space-y-6">
                  <LoadingSkeleton count={2} className="h-64" />
                </div>
                <div className="lg:col-span-5 space-y-6">
                  <LoadingSkeleton count={3} className="h-44" />
                </div>
              </div>
            </div>
          ) : isError || !incident ? (
            <ErrorCard
              title="Incident Unavailable"
              message={error instanceof Error ? error.message : `Weather incident with ID '${cleanId}' does not exist.`}
              onRetry={() => refetch()}
            />
          ) : (
            <div className="space-y-6">
              {/* Header Hero Banner */}
              <div className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-7 shadow-2xs space-y-4">
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <div className="flex items-center space-x-2">
                    <span
                      className={`inline-flex items-center rounded-lg px-2.5 py-1 text-xs font-bold border ${severityStyle?.bgClass} ${severityStyle?.borderClass}`}
                    >
                      {formatHazardCategory(incident.category?.code)}
                    </span>
                    <span
                      className={`inline-flex items-center rounded-lg px-2.5 py-1 text-xs font-extrabold ${verificationStyle?.bgClass}`}
                    >
                      {verificationStyle?.label}
                    </span>
                  </div>

                  <span
                    className={`inline-flex items-center space-x-1.5 rounded-full px-3 py-1 text-xs font-bold border ${readinessStyle?.badgeClass}`}
                  >
                    <span className={`h-2 w-2 rounded-full ${readinessStyle?.pillBg}`} aria-hidden="true" />
                    <span>{readinessStyle?.label}</span>
                  </span>
                </div>

                <div>
                  <h1 className="text-xl sm:text-3xl font-extrabold text-slate-900 tracking-tight leading-snug">
                    {incident.title}
                  </h1>

                  <div className="mt-3 flex items-center space-x-4 text-xs text-slate-500 flex-wrap gap-y-1">
                    <div className="flex items-center space-x-1.5">
                      <Clock className="h-3.5 w-3.5 text-slate-400" aria-hidden="true" />
                      <span>Reported: {formatDateTime(incident.occurred_at || incident.created_at)}</span>
                    </div>

                    <div className="flex items-center space-x-1.5">
                      <MapPin className="h-3.5 w-3.5 text-blue-600" aria-hidden="true" />
                      <span className="font-semibold text-slate-700">
                        {incident.location?.name || (hasCoords ? `${incident.location.latitude?.toFixed(4)}, ${incident.location.longitude?.toFixed(4)}` : 'Location Unresolved')}
                      </span>
                    </div>
                  </div>
                </div>

                {incident.description && (
                  <p className="text-xs sm:text-sm text-slate-700 leading-relaxed pt-2 border-t border-slate-100">
                    {incident.description}
                  </p>
                )}

                {/* Feature B4: Community Crowd Validation Widget */}
                <FeedbackWidget incidentId={incident.id} />
              </div>

              {/* 2-Column Responsive Layout */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
                {/* Left Column: Location Map & Media & Observations & Duplicates */}
                <div className="lg:col-span-7 space-y-6">
                  {/* Location & Mini Map Section */}
                  <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-500 flex items-center space-x-1.5">
                        <MapPin className="h-4 w-4 text-blue-600" aria-hidden="true" />
                        <span>Geographic Position</span>
                      </h3>
                      {hasCoords && (
                        <span className="font-mono text-[11px] text-slate-400">
                          {incident.location.latitude?.toFixed(4)}, {incident.location.longitude?.toFixed(4)}
                        </span>
                      )}
                    </div>

                    {hasCoords ? (
                      <div className="h-56 rounded-xl overflow-hidden border border-slate-200 relative z-0">
                        <MapContainer
                          center={[incident.location.latitude as number, incident.location.longitude as number]}
                          zoom={12}
                          scrollWheelZoom={false}
                          className="h-full w-full"
                        >
                          <TileLayer
                            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                          />
                          <Marker
                            position={[incident.location.latitude as number, incident.location.longitude as number]}
                            icon={miniMarkerIcon}
                          />
                        </MapContainer>
                      </div>
                    ) : (
                      <div className="rounded-xl border border-slate-200 bg-slate-50 p-6 text-center text-xs text-slate-500">
                        No precise geographic coordinates are available for this incident.
                      </div>
                    )}
                  </div>

                  {/* Attached Media Gallery */}
                  {incident.media && incident.media.length > 0 && (
                    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs space-y-3">
                      <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-500">
                        Attached Citizen Media ({incident.media.length})
                      </h3>
                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                        {incident.media.map((med) => {
                          const isError = mediaErrorMap[med.id];
                          const isVid = med.media_type === 'VIDEO';

                          return (
                            <div
                              key={med.id}
                              className="relative h-32 rounded-xl overflow-hidden border border-slate-200 bg-slate-900 flex items-center justify-center group"
                            >
                              {!isError ? (
                                isVid ? (
                                  <video src={med.url} controls className="h-full w-full object-cover" onError={() => setMediaErrorMap((prev) => ({ ...prev, [med.id]: true }))} />
                                ) : (
                                  <a href={med.url} target="_blank" rel="noopener noreferrer" className="block h-full w-full">
                                    <img
                                      src={med.url}
                                      alt="Attached incident media"
                                      className="h-full w-full object-cover group-hover:scale-105 transition-transform"
                                      onError={() => setMediaErrorMap((prev) => ({ ...prev, [med.id]: true }))}
                                    />
                                  </a>
                                )
                              ) : (
                                <div className="p-3 text-center text-slate-400 text-[10px]">
                                  <ImageOff className="h-5 w-5 mx-auto mb-1 text-slate-500" aria-hidden="true" />
                                  <span>Media unavailable</span>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Physical Observations */}
                  <PhysicalObservationsSection
                    incidentId={incident.id}
                    totalCount={incident.summaries?.observation_count}
                  />

                  {/* Duplicate Cluster */}
                  <DuplicateClusterSection
                    incidentId={incident.id}
                    clusterSize={incident.summaries?.duplicate_cluster_size}
                    verificationStatus={incident.verification?.status}
                  />
                </div>

                {/* Right Column: Credibility, Intelligence, Evidence */}
                <div className="lg:col-span-5 space-y-6">
                  {/* Credibility Section */}
                  <CredibilitySection
                    incidentId={incident.id}
                    initialSummary={incident.credibility}
                  />

                  {/* Intelligence Orchestration Status */}
                  <IntelligenceStatusSection
                    incidentId={incident.id}
                    initialSummary={incident.intelligence_status}
                  />

                  {/* Digital Evidence */}
                  <LinkedEvidenceSection
                    incidentId={incident.id}
                    totalCount={incident.summaries?.evidence_count}
                  />
                </div>
              </div>
            </div>
          )}
        </div>
      </main>

      <Footer />
    </div>
  );
};
