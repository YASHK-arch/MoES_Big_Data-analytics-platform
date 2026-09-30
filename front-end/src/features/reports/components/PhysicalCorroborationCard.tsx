import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  CloudSun,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Radio,
  Cpu,
  Sparkles,
  MapPin,
  Clock,
  Gauge,
} from 'lucide-react';
import { PhysicalCorroborationBlock, PhysicalCorroborationItem } from '@/types';

export interface PhysicalCorroborationCardProps {
  corroboration?: PhysicalCorroborationBlock | null;
  enabled?: boolean;
}

export const PhysicalCorroborationCard: React.FC<PhysicalCorroborationCardProps> = ({
  corroboration,
  enabled,
}) => {
  const { t } = useTranslation();

  // Hide if explicitly disabled via prop or environment flag
  const isEnvEnabled =
    typeof import.meta !== 'undefined' &&
    import.meta.env &&
    import.meta.env.VITE_PHYSICAL_CORROBORATION_ENABLED !== 'false';

  const isEnabled = enabled !== undefined ? enabled : isEnvEnabled;
  if (!isEnabled || !corroboration) {
    return null;
  }

  const getVerdictBadge = (verdict: string) => {
    switch (verdict.toUpperCase()) {
      case 'SUPPORTS':
        return (
          <span
            data-testid="verdict-supports"
            className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-200"
          >
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
            {t('physicalCorroboration.verdictSupports', 'SUPPORTS')}
          </span>
        );
      case 'CONTRADICTS':
        return (
          <span
            data-testid="verdict-contradicts"
            className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-rose-50 text-rose-700 border border-rose-200"
          >
            <XCircle className="w-3.5 h-3.5 text-rose-600" />
            {t('physicalCorroboration.verdictContradicts', 'CONTRADICTS')}
          </span>
        );
      case 'NEUTRAL':
      default:
        return (
          <span
            data-testid="verdict-neutral"
            className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-amber-50 text-amber-700 border border-amber-200"
          >
            <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
            {t('physicalCorroboration.verdictNeutral', 'NEUTRAL')}
          </span>
        );
    }
  };

  const getSourceBadge = (item: PhysicalCorroborationItem) => {
    if (item.is_simulated) {
      return (
        <span
          data-testid="source-badge-simulated"
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-semibold bg-purple-50 text-purple-700 border border-purple-200"
        >
          <Sparkles className="w-3 h-3 text-purple-600" />
          {t('physicalCorroboration.sourceSimulated', 'SIMULATED')}
        </span>
      );
    }
    if (item.source_type === 'STATION') {
      return (
        <span
          data-testid="source-badge-station"
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-semibold bg-blue-50 text-blue-700 border border-blue-200"
        >
          <Radio className="w-3 h-3 text-blue-600" />
          {t('physicalCorroboration.sourceStation', 'STATION')}
        </span>
      );
    }
    return (
      <span
        data-testid="source-badge-model"
        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200"
      >
        <Cpu className="w-3 h-3 text-indigo-600" />
        {t('physicalCorroboration.sourceModel', 'MODEL')}
      </span>
    );
  };

  return (
    <div
      data-testid="physical-corroboration-card"
      className="rounded-2xl border border-slate-200 bg-white p-5 md:p-6 shadow-sm space-y-4"
    >
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-sky-50 text-sky-600">
              <CloudSun className="h-5 w-5" />
            </div>
            <h3 className="text-base font-bold text-slate-900">
              {t('physicalCorroboration.title', 'Physical Weather Corroboration')}
            </h3>
          </div>
          <p className="text-xs text-slate-500">
            {t(
              'physicalCorroboration.subtitle',
              'Independent atmospheric observations corroborated against numerical models and weather stations'
            )}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {corroboration.is_simulated && (
            <span
              data-testid="overall-simulated-badge"
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-purple-50 text-purple-700 border border-purple-200"
            >
              <Sparkles className="w-3 h-3 text-purple-600" />
              DEMO SIMULATION
            </span>
          )}
          {getVerdictBadge(corroboration.overall_verdict)}
        </div>
      </div>

      {/* Observation Items List */}
      {corroboration.items.length === 0 ? (
        <p className="text-xs text-slate-400 italic py-2">
          {t('physicalCorroboration.noData', 'No physical observations available for this incident window')}
        </p>
      ) : (
        <div className="space-y-3 pt-2">
          {corroboration.items.map((item, idx) => (
            <div
              key={item.id || `corrob-${idx}`}
              data-testid="physical-observation-item"
              className="rounded-xl border border-slate-100 bg-slate-50/70 p-4 space-y-3 text-xs"
            >
              {/* Item Header */}
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200/60 pb-2">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-slate-800 uppercase tracking-wide">
                    {item.variable.replace(/_/g, ' ')}
                  </span>
                  {getSourceBadge(item)}
                  <span className="text-[11px] text-slate-500 font-medium">
                    ({item.source})
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  {item.provider_status !== 'OK' && (
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-amber-100 text-amber-800">
                      {item.provider_status}
                    </span>
                  )}
                  {getVerdictBadge(item.verdict)}
                </div>
              </div>

              {/* Metric Values Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-slate-600">
                <div className="flex items-center gap-1.5">
                  <Gauge className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                  <div>
                    <span className="block text-[10px] text-slate-400 uppercase font-medium">
                      {t('physicalCorroboration.observed', 'Observed')}
                    </span>
                    <span className="font-semibold text-slate-900">
                      {item.observed_value !== null && item.observed_value !== undefined
                        ? `${item.observed_value} ${item.unit}`
                        : 'N/A'}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-1.5">
                  <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                  <div>
                    <span className="block text-[10px] text-slate-400 uppercase font-medium">
                      {t('physicalCorroboration.distance', 'Distance')}
                    </span>
                    <span className="font-semibold text-slate-900">
                      {item.distance_km !== null && item.distance_km !== undefined
                        ? `${item.distance_km.toFixed(1)} km`
                        : 'N/A'}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                  <div>
                    <span className="block text-[10px] text-slate-400 uppercase font-medium">
                      {t('physicalCorroboration.timeGap', 'Time Difference')}
                    </span>
                    <span className="font-semibold text-slate-900">
                      {item.time_gap_hours !== null && item.time_gap_hours !== undefined
                        ? `${item.time_gap_hours.toFixed(1)} h`
                        : 'N/A'}
                    </span>
                  </div>
                </div>

                <div>
                  <span className="block text-[10px] text-slate-400 uppercase font-medium">
                    {t('physicalCorroboration.contribution', 'Score Impact')}
                  </span>
                  <span
                    className={`font-semibold ${
                      item.contribution > 0
                        ? 'text-emerald-700'
                        : item.contribution < 0
                          ? 'text-rose-700'
                          : 'text-slate-700'
                    }`}
                  >
                    {item.contribution > 0 ? `+${item.contribution.toFixed(4)}` : item.contribution.toFixed(4)}
                  </span>
                </div>
              </div>

              {/* Explanation */}
              {item.explanation && (
                <p className="text-[11px] leading-relaxed text-slate-700 bg-white/90 p-2.5 rounded-lg border border-slate-200/70">
                  <span className="font-bold text-slate-800">Explanation: </span>
                  {item.explanation}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
