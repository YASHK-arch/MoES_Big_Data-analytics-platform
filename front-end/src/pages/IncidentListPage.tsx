// Public Operational Incident Intelligence Feed & Search Directory

import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Layers, ChevronLeft, ChevronRight, RefreshCw } from 'lucide-react';
import { Navbar } from '@/components/layout/Navbar';
import { Footer } from '@/components/layout/Footer';
import { IncidentCard } from '@/features/incidents/IncidentCard';
import { IncidentFilters, IncidentFilterState } from '@/features/incidents/IncidentFilters';
import { LoadingSkeleton } from '@/components/common/LoadingSkeleton';
import { EmptyState } from '@/components/common/EmptyState';
import { ErrorCard } from '@/components/common/ErrorCard';
import { incidentApi } from '@/services/incidentApi';
import { incidentKeys } from '@/lib/queryKeys';
import { IncidentListQueryParams } from '@/types';

export const IncidentListPage: React.FC = () => {
  const [filters, setFilters] = useState<IncidentFilterState>({
    searchQuery: '',
    category: 'ALL',
    severity: 'ALL',
    verification_status: 'ALL',
    readiness: 'ALL',
  });

  const [page, setPage] = useState<number>(1);
  const pageSize = 20;

  // Reset page to 1 when filters change
  const handleFilterChange = (newFilters: IncidentFilterState) => {
    setFilters(newFilters);
    setPage(1);
  };

  const handleResetFilters = () => {
    setFilters({
      searchQuery: '',
      category: 'ALL',
      severity: 'ALL',
      verification_status: 'ALL',
      readiness: 'ALL',
    });
    setPage(1);
  };

  const queryParams: IncidentListQueryParams = useMemo(() => {
    const p: IncidentListQueryParams = {
      page,
      page_size: pageSize,
    };
    if (filters.category !== 'ALL') p.category = filters.category;
    if (filters.severity !== 'ALL') p.severity = filters.severity;
    if (filters.verification_status !== 'ALL') p.verification_status = filters.verification_status;
    if (filters.readiness !== 'ALL') p.readiness = filters.readiness;
    if (filters.min_credibility !== undefined) p.min_credibility = filters.min_credibility;
    if (filters.hide_demo) p.hide_demo = true;
    return p;
  }, [filters, page]);

  const { data: response, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: incidentKeys.list(queryParams as Record<string, unknown>),
    queryFn: ({ signal }) => incidentApi.listIncidents(queryParams, signal),
    staleTime: 1000 * 30, // 30 seconds
  });

  const pagination = response?.pagination;

  // Search filter applied on top of server data
  const incidents = useMemo(() => {
    const raw = response?.data || [];
    const query = filters.searchQuery.trim().toLowerCase();
    if (!query) return raw;

    return raw.filter((inc) => {
      const matchTrack = inc.tracking_id.toLowerCase().includes(query);
      const matchTitle = inc.title.toLowerCase().includes(query);
      const matchLoc = inc.location?.name?.toLowerCase().includes(query) ?? false;
      return matchTrack || matchTitle || matchLoc;
    });
  }, [response?.data, filters.searchQuery]);

  return (
    <div className="flex min-h-screen flex-col bg-slate-50/50 text-slate-900">
      <Navbar />

      <main className="flex-1 py-8 sm:py-10">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 space-y-6">
          {/* Header Banner */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <div className="flex items-center space-x-2 text-blue-600 font-bold text-xs uppercase tracking-wider">
                <Layers className="h-4 w-4" aria-hidden="true" />
                <span>Incident Intelligence Feed</span>
              </div>
              <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight mt-1">
                National Disaster & Weather Incidents
              </h1>
              <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-2xl">
                Real-time situational awareness feed enriched with machine credibility, AWS observation corroboration, and digital evidence.
              </p>
            </div>

            <button
              type="button"
              onClick={() => refetch()}
              disabled={isFetching}
              className="self-start sm:self-auto inline-flex items-center space-x-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-bold text-slate-700 shadow-2xs hover:bg-slate-50 disabled:opacity-50 transition-colors"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? 'animate-spin' : ''}`} aria-hidden="true" />
              <span>Refresh Feed</span>
            </button>
          </div>

          {/* Filter Bar */}
          <IncidentFilters
            filters={filters}
            onChange={handleFilterChange}
            onReset={handleResetFilters}
            totalRecords={pagination?.total_records}
          />

          {/* Content Area */}
          {isLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5">
              <LoadingSkeleton count={6} className="h-48 w-full" />
            </div>
          ) : isError ? (
            <ErrorCard
              title="Feed Unavailable"
              message={error instanceof Error ? error.message : 'Failed to retrieve incident feed.'}
              onRetry={() => refetch()}
            />
          ) : incidents.length === 0 ? (
            <EmptyState
              title="No Incidents Match Filters"
              description="Try adjusting your search criteria, hazard categories, or severity filters to view active reports."
              actionLabel="Reset All Filters"
              onAction={handleResetFilters}
            />
          ) : (
            <div className="space-y-6">
              {/* Incident Cards Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5">
                {incidents.map((incident) => (
                  <IncidentCard key={incident.id || incident.tracking_id} incident={incident} />
                ))}
              </div>

              {/* Pagination Controls */}
              {pagination && pagination.total_pages > 1 && (
                <nav
                  className="flex items-center justify-between border-t border-slate-200 bg-white px-4 py-3 sm:px-6 rounded-2xl shadow-2xs"
                  aria-label="Incident feed pagination"
                >
                  <div className="flex flex-1 justify-between sm:hidden">
                    <button
                      type="button"
                      disabled={!pagination.has_prev}
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      className="inline-flex items-center rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-bold text-slate-700 disabled:opacity-40"
                    >
                      Previous
                    </button>
                    <button
                      type="button"
                      disabled={!pagination.has_next}
                      onClick={() => setPage((p) => p + 1)}
                      className="ml-3 inline-flex items-center rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-bold text-slate-700 disabled:opacity-40"
                    >
                      Next
                    </button>
                  </div>

                  <div className="hidden sm:flex sm:flex-1 sm:items-center sm:justify-between">
                    <div>
                      <p className="text-xs text-slate-600 font-medium">
                        Showing page <span className="font-bold text-slate-900">{pagination.page}</span> of{' '}
                        <span className="font-bold text-slate-900">{pagination.total_pages}</span> (
                        <span className="font-bold text-slate-900">{pagination.total_records}</span> total incidents)
                      </p>
                    </div>

                    <div className="flex items-center space-x-2">
                      <button
                        type="button"
                        disabled={!pagination.has_prev}
                        onClick={() => setPage((p) => Math.max(1, p - 1))}
                        className="inline-flex items-center space-x-1 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-bold text-slate-700 hover:bg-slate-50 disabled:opacity-40 transition-colors"
                      >
                        <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                        <span>Previous</span>
                      </button>
                      <button
                        type="button"
                        disabled={!pagination.has_next}
                        onClick={() => setPage((p) => p + 1)}
                        className="inline-flex items-center space-x-1 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-bold text-slate-700 hover:bg-slate-50 disabled:opacity-40 transition-colors"
                      >
                        <span>Next</span>
                        <ChevronRight className="h-4 w-4" aria-hidden="true" />
                      </button>
                    </div>
                  </div>
                </nav>
              )}
            </div>
          )}
        </div>
      </main>

      <Footer />
    </div>
  );
};
