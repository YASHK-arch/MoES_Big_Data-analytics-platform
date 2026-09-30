import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { AlertCircle, FileSearch } from 'lucide-react';
import { Navbar } from '@/components/layout/Navbar';
import { Footer } from '@/components/layout/Footer';
import { ReportDetailData } from '@/types';
import { fetchReportByTrackingId } from '@/services/reportApi';
import { TrackingSearchHeader } from '@/features/tracking/TrackingSearchHeader';
import { ReportStatusBanner } from '@/features/tracking/ReportStatusBanner';
import { VerificationPipelineCard } from '@/features/tracking/VerificationPipelineCard';
import { TrustScoreCard } from '@/features/tracking/TrustScoreCard';
import { LocationCard } from '@/features/tracking/LocationCard';
import { SubmittedEvidenceCard } from '@/features/tracking/SubmittedEvidenceCard';
import { PhysicalCorroborationCard } from '@/features/reports/components/PhysicalCorroborationCard';

export const TrackReportPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryId = searchParams.get('id') || '';

  const [searchedId, setSearchedId] = useState<string>(queryId);
  const [report, setReport] = useState<ReportDetailData | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const performLookup = React.useCallback(async (idToSearch: string) => {
    const cleanId = idToSearch.trim();
    if (!cleanId) return;

    setIsLoading(true);
    setErrorMessage(null);
    setReport(null);

    // Update query string in URL
    setSearchParams({ id: cleanId });

    try {
      const response = await fetchReportByTrackingId(cleanId);
      setReport(response.data);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage('Failed to retrieve report status. Please check the tracking ID and try again.');
      }
    } finally {
      setIsLoading(false);
    }
  }, [setSearchParams]);

  useEffect(() => {
    if (queryId) {
      setSearchedId(queryId);
      performLookup(queryId);
    }
  }, [queryId, performLookup]);

  const handleSearch = (newId: string) => {
    setSearchedId(newId);
    performLookup(newId);
  };

  return (
    <div className="flex min-h-screen flex-col bg-slate-50/50 text-slate-900">
      {/* Navigation Header */}
      <Navbar />

      {/* Main Content */}
      <main className="flex-1 py-8 sm:py-12">
        <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
          {/* Page Heading matching Stitch Reference */}
          <div className="text-center mb-8 sm:mb-10">
            <h1 className="text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl">
              Track Incident Report
            </h1>
            <p className="mt-3 text-sm sm:text-base leading-relaxed text-slate-600 max-w-2xl mx-auto">
              Enter your tracking ID below to view the real-time status and verification progress of your submitted report.
            </p>

            {/* Search Bar */}
            <div className="mt-6">
              <TrackingSearchHeader
                initialTrackingId={searchedId}
                onSearch={handleSearch}
                isLoading={isLoading}
              />
            </div>
          </div>

          {/* Loading State */}
          {isLoading && (
            <div className="space-y-6 animate-pulse">
              <div className="h-28 rounded-2xl bg-slate-200" />
              <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                <div className="h-96 rounded-2xl bg-slate-200 lg:col-span-2" />
                <div className="space-y-6 lg:col-span-1">
                  <div className="h-44 rounded-2xl bg-slate-200" />
                  <div className="h-48 rounded-2xl bg-slate-200" />
                </div>
              </div>
            </div>
          )}

          {/* Error State */}
          {!isLoading && errorMessage && (
            <div className="mx-auto max-w-2xl rounded-2xl border border-rose-200 bg-rose-50 p-6 text-center shadow-sm">
              <div className="flex justify-center text-rose-600 mb-3">
                <AlertCircle className="h-10 w-10" />
              </div>
              <h3 className="text-lg font-bold text-rose-950">Report Lookup Notice</h3>
              <p className="mt-2 text-sm text-rose-800 leading-relaxed">{errorMessage}</p>
              <p className="mt-3 text-xs text-rose-600">
                Tracking IDs follow the format <span className="font-mono font-bold">RPT-YYYYMMDD-XXXX</span>. Please check for typos.
              </p>
            </div>
          )}

          {/* Report Found State (Matching Stitch Composition) */}
          {!isLoading && report && (
            <div className="space-y-6">
              {/* Top Summary Banner */}
              <ReportStatusBanner report={report} />

              {/* 2-Column Responsive Layout on Desktop / 1-Column on Mobile */}
              <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                {/* Left Column: Verification Stepper Pipeline */}
                <div className="lg:col-span-2">
                  <VerificationPipelineCard report={report} />
                </div>

                {/* Right Column: Trust Score, Physical Corroboration, Location & Evidence */}
                <div className="space-y-6 lg:col-span-1">
                  <TrustScoreCard report={report} />
                  <PhysicalCorroborationCard corroboration={report.physical_corroboration} />
                  <LocationCard location={report.location} />
                  <SubmittedEvidenceCard media={report.media} />
                </div>
              </div>
            </div>
          )}

          {/* Initial State (Before Searching) */}
          {!isLoading && !report && !errorMessage && (
            <div className="mx-auto max-w-lg rounded-2xl border border-dashed border-slate-300 bg-white/60 p-8 text-center">
              <div className="flex justify-center text-slate-400 mb-3">
                <FileSearch className="h-10 w-10" />
              </div>
              <h3 className="text-base font-bold text-slate-800">No Report Selected</h3>
              <p className="mt-1.5 text-xs leading-relaxed text-slate-500">
                Enter your alphanumeric tracking code (e.g., <span className="font-mono font-semibold">RPT-20260829-K8L9</span>) above to view report status, evidence, and verification timeline.
              </p>
            </div>
          )}
        </div>
      </main>

      {/* Footer */}
      <Footer />
    </div>
  );
};
