import React, { useState } from 'react';
import { ThumbsUp, AlertOctagon, CheckCircle2, Loader2 } from 'lucide-react';
import { apiClient } from '@/services/client';

interface FeedbackWidgetProps {
  incidentId: string;
  initialConfirmCount?: number;
  initialDisputeCount?: number;
}

export const FeedbackWidget: React.FC<FeedbackWidgetProps> = ({
  incidentId,
  initialConfirmCount = 0,
  initialDisputeCount = 0,
}) => {
  const [confirmCount, setConfirmCount] = useState(initialConfirmCount);
  const [disputeCount, setDisputeCount] = useState(initialDisputeCount);
  const [userVoted, setUserVoted] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleVote = async (type: 'CONFIRM' | 'DISPUTE') => {
    if (userVoted || isSubmitting) return;

    setIsSubmitting(true);
    try {
      const res = await apiClient<{
        data: { confirm_count: number; dispute_count: number; voted_type: string };
      }>(`/incidents/${incidentId}/feedback`, {
        method: 'POST',
        body: JSON.stringify({ vote_type: type }),
      });

      setConfirmCount(res.data.confirm_count);
      setDisputeCount(res.data.dispute_count);
      setUserVoted(type);
    } catch {
      // Ignore voting errors quietly
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
            Community Crowd Validation — "Still Accurate?"
          </h4>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Are you near this location? Confirm ground reality or dispute false reports.
          </p>
        </div>
        {userVoted && (
          <span className="flex items-center space-x-1 text-[10px] font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">
            <CheckCircle2 className="h-3 w-3 text-emerald-500" />
            <span>Vote Recorded</span>
          </span>
        )}
      </div>

      <div className="flex items-center space-x-3">
        <button
          type="button"
          disabled={Boolean(userVoted) || isSubmitting}
          onClick={() => handleVote('CONFIRM')}
          className={`flex-1 flex items-center justify-center space-x-2 py-2 px-3 rounded-lg border text-xs font-bold transition-all ${
            userVoted === 'CONFIRM'
              ? 'bg-emerald-600 text-white border-emerald-600 shadow-xs'
              : 'bg-white text-slate-800 border-slate-300 hover:border-emerald-500 hover:bg-emerald-50/50'
          } disabled:opacity-75`}
        >
          {isSubmitting && userVoted === null ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <ThumbsUp className="h-3.5 w-3.5 text-emerald-600" />
          )}
          <span>Confirm Active ({confirmCount})</span>
        </button>

        <button
          type="button"
          disabled={Boolean(userVoted) || isSubmitting}
          onClick={() => handleVote('DISPUTE')}
          className={`flex-1 flex items-center justify-center space-x-2 py-2 px-3 rounded-lg border text-xs font-bold transition-all ${
            userVoted === 'DISPUTE'
              ? 'bg-rose-600 text-white border-rose-600 shadow-xs'
              : 'bg-white text-slate-800 border-slate-300 hover:border-rose-500 hover:bg-rose-50/50'
          } disabled:opacity-75`}
        >
          <AlertOctagon className="h-3.5 w-3.5 text-rose-600" />
          <span>Dispute / Cleared ({disputeCount})</span>
        </button>
      </div>
    </div>
  );
};
