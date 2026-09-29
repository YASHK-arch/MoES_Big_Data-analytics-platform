import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  FileText,
  Clock,
  MapPin,
  PlusCircle,
  Loader2,
  CheckCircle2,
  XCircle,
  HelpCircle,
  TrendingUp,
} from 'lucide-react';
import { Navbar } from '@/components/layout/Navbar';
import { useAuth } from '@/context/AuthContext';
import { authApi } from '@/services/authApi';

interface MyReportItem {
  id: string;
  tracking_id: string;
  title: string;
  category: string;
  severity: string;
  verification_status: string;
  credibility_score: number;
  credibility_reason?: string;
  location_name?: string;
  latitude: number;
  longitude: number;
  occurred_at?: string;
}

export const MyReportsPage: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [reports, setReports] = useState<MyReportItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    const fetchReports = async () => {
      setLoading(true);
      try {
        const res = await authApi.getMyReports();
        if (mounted) {
          setReports(res.data || []);
        }
      } catch (err: unknown) {
        if (mounted) {
          setError(err instanceof Error ? err.message : 'Failed to load submitted reports');
        }
      } finally {
        if (mounted) setLoading(false);
      }
    };
    fetchReports();
    return () => {
      mounted = false;
    };
  }, []);

  const getStatusBadge = (status: string) => {
    switch (status.toUpperCase()) {
      case 'VERIFIED':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
            <span>Verified by DEOC</span>
          </span>
        );
      case 'UNDER_REVIEW':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-200">
            <Clock className="h-3.5 w-3.5 text-amber-600" />
            <span>Under Review</span>
          </span>
        );
      case 'REJECTED':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full text-xs font-bold bg-rose-100 text-rose-800 border border-rose-200">
            <XCircle className="h-3.5 w-3.5 text-rose-600" />
            <span>Rejected</span>
          </span>
        );
      case 'DUPLICATE':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full text-xs font-bold bg-purple-100 text-purple-800 border border-purple-200">
            <HelpCircle className="h-3.5 w-3.5 text-purple-600" />
            <span>Duplicate Clustered</span>
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full text-xs font-bold bg-blue-100 text-blue-800 border border-blue-200">
            <Clock className="h-3.5 w-3.5 text-blue-600" />
            <span>Pending Review</span>
          </span>
        );
    }
  };

  const getSeverityBadge = (severity: string) => {
    switch (severity.toUpperCase()) {
      case 'SEVERE':
        return <span className="px-2 py-0.5 rounded text-[10px] font-extrabold bg-red-600 text-white uppercase">Severe</span>;
      case 'HIGH':
        return <span className="px-2 py-0.5 rounded text-[10px] font-extrabold bg-orange-600 text-white uppercase">High</span>;
      case 'MODERATE':
        return <span className="px-2 py-0.5 rounded text-[10px] font-extrabold bg-amber-500 text-white uppercase">Moderate</span>;
      default:
        return <span className="px-2 py-0.5 rounded text-[10px] font-extrabold bg-blue-500 text-white uppercase">Low</span>;
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col font-sans antialiased">
      <Navbar />

      <main className="flex-1 max-w-5xl w-full mx-auto p-4 sm:p-6 lg:p-8 space-y-6">
        {/* Page Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-white p-6 rounded-2xl border border-slate-200 shadow-xs">
          <div className="space-y-1">
            <div className="flex items-center space-x-2">
              <span className="text-xs font-bold uppercase tracking-wider text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-full">
                Citizen Incident History
              </span>
            </div>
            <h1 className="text-2xl font-black text-slate-900">
              My Submitted Weather Reports
            </h1>
            <p className="text-xs sm:text-sm text-slate-500">
              Track the verification status, algorithmic credibility score, and review notes of reports submitted by{' '}
              <strong className="text-slate-800">{user?.full_name || user?.email}</strong>.
            </p>
          </div>

          <button
            type="button"
            onClick={() => navigate('/report')}
            className="inline-flex items-center justify-center space-x-2 rounded-xl bg-blue-600 hover:bg-blue-700 px-4 py-2.5 text-xs font-bold text-white shadow-xs transition-all cursor-pointer shrink-0"
          >
            <PlusCircle className="h-4 w-4" />
            <span>Submit New Report</span>
          </button>
        </div>

        {/* Loading State */}
        {loading && (
          <div className="flex flex-col items-center justify-center py-16 space-y-3 bg-white rounded-2xl border border-slate-200">
            <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
            <span className="text-xs font-semibold text-slate-500">Loading your submitted reports...</span>
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="p-4 rounded-xl border border-red-200 bg-red-50 text-xs text-red-700 font-medium">
            {error}
          </div>
        )}

        {/* Empty State */}
        {!loading && !error && reports.length === 0 && (
          <div className="text-center py-16 px-4 bg-white rounded-2xl border border-slate-200 shadow-xs space-y-4">
            <div className="inline-flex h-16 w-16 items-center justify-center rounded-full bg-slate-100 text-slate-400">
              <FileText className="h-8 w-8" />
            </div>
            <div className="space-y-1 max-w-sm mx-auto">
              <h3 className="text-base font-bold text-slate-900">No Eyewitness Reports Yet</h3>
              <p className="text-xs text-slate-500">
                You haven&apos;t submitted any severe weather or flood reports from this account. Your contributions help disaster response teams verify real-time conditions.
              </p>
            </div>
            <button
              type="button"
              onClick={() => navigate('/report')}
              className="inline-flex items-center space-x-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 px-4 py-2.5 text-xs font-bold text-white transition-all cursor-pointer"
            >
              <PlusCircle className="h-4 w-4" />
              <span>Submit Your First Report</span>
            </button>
          </div>
        )}

        {/* Reports List */}
        {!loading && !error && reports.length > 0 && (
          <div className="space-y-3">
            {reports.map((report) => (
              <div
                key={report.id}
                className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs hover:border-slate-300 transition-all space-y-3"
              >
                <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2">
                  <div className="space-y-1">
                    <div className="flex items-center space-x-2">
                      <span className="font-mono text-[11px] font-bold text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
                        {report.tracking_id}
                      </span>
                      {getSeverityBadge(report.severity)}
                      <span className="text-xs font-semibold text-slate-600">
                        {report.category}
                      </span>
                    </div>
                    <h3 className="text-base font-extrabold text-slate-900">
                      {report.title}
                    </h3>
                  </div>

                  <div className="shrink-0">
                    {getStatusBadge(report.verification_status)}
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 border-t border-slate-100 text-xs text-slate-600">
                  <div className="flex items-center space-x-2">
                    <MapPin className="h-4 w-4 text-slate-400 shrink-0" />
                    <span className="truncate">
                      {report.location_name || `${report.latitude.toFixed(4)}°, ${report.longitude.toFixed(4)}°`}
                    </span>
                  </div>

                  <div className="flex items-center space-x-2">
                    <Clock className="h-4 w-4 text-slate-400 shrink-0" />
                    <span>
                      {report.occurred_at ? new Date(report.occurred_at).toLocaleString() : 'Recent'}
                    </span>
                  </div>

                  <div className="flex items-center space-x-2">
                    <TrendingUp className="h-4 w-4 text-emerald-600 shrink-0" />
                    <span>
                      Credibility Score: <strong className="text-slate-900">{(report.credibility_score * 100).toFixed(0)}%</strong>
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
};
