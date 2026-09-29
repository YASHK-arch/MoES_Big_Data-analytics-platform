import React from 'react';
import { Shield } from 'lucide-react';
import { ReportDetailData } from '@/types';

interface TrustScoreCardProps {
  report: ReportDetailData;
}

export const TrustScoreCard: React.FC<TrustScoreCardProps> = ({ report }) => {
  // Real credibility score scaled to 100 or baseline
  const scoreValue = Math.round((report.credibility_score || 0) * 100);

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 md:p-6 shadow-sm">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-bold text-slate-900">Automated Trust Score</h3>
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
          <Shield className="h-5 w-5" />
        </div>
      </div>

      <div className="mt-3 flex items-baseline space-x-2">
        <span className="text-4xl font-extrabold tracking-tight text-blue-600">
          {scoreValue}
        </span>
        <span className="text-sm font-semibold text-slate-400">/ 100</span>
      </div>

      {report.credibility_reason ? (
        <p className="mt-2 text-xs leading-relaxed text-blue-900 bg-blue-50/80 p-2.5 rounded-xl border border-blue-100/80 font-medium">
          <span className="font-bold text-blue-700">Reason: </span>
          {report.credibility_reason}
        </p>
      ) : (
        <p className="mt-2 text-xs leading-relaxed text-slate-500">
          Score indicates initial heuristic credibility based on geographical proximity and evidence.
        </p>
      )}

      <div className="mt-4 divide-y divide-slate-100 text-xs">
        <div className="flex items-center justify-between py-2">
          <span className="text-slate-500">Location Accuracy</span>
          <span className="font-semibold text-emerald-700">Verified (GPS)</span>
        </div>
        <div className="flex items-center justify-between py-2">
          <span className="text-slate-500">Media Metadata</span>
          <span className="font-semibold text-slate-800">
            {report.media.length > 0 ? `${report.media.length} Attached` : 'No Media'}
          </span>
        </div>
        <div className="flex items-center justify-between py-2">
          <span className="text-slate-500">Intake Source</span>
          <span className="font-semibold text-slate-800">Citizen Web Portal</span>
        </div>
      </div>
    </div>
  );
};
