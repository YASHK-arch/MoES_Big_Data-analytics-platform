import React from 'react';
import {
  CloudRain,
  Droplet,
  Zap,
  Wind,
  ThermometerSun,
  CloudFog,
  Sparkles,
  MoreHorizontal,
} from 'lucide-react';
import { UseFormReturn } from 'react-hook-form';
import { CitizenReportFormValues } from '@/types';

interface CategorySectionProps {
  form: UseFormReturn<CitizenReportFormValues>;
}

const CATEGORIES = [
  { code: 'HEAVY_RAINFALL', label: 'Heavy Rainfall', icon: CloudRain },
  { code: 'FLOOD_WATERLOGGING', label: 'Flooding', icon: Droplet },
  { code: 'THUNDERSTORM_LIGHTNING', label: 'Thunderstorm', icon: Zap },
  { code: 'STRONG_WIND', label: 'Strong Wind', icon: Wind },
  { code: 'HEATWAVE', label: 'Heatwave', icon: ThermometerSun },
  { code: 'FOG', label: 'Fog', icon: CloudFog },
  { code: 'DUST_STORM', label: 'Dust Storm', icon: Sparkles },
  { code: 'OTHER', label: 'Other', icon: MoreHorizontal },
];

export const CategorySection: React.FC<CategorySectionProps> = ({ form }) => {
  const { setValue, watch, formState: { errors } } = form;
  const selectedCategory = watch('category_code');

  const handleSelectCategory = (code: string) => {
    setValue('category_code', code, { shouldValidate: true });
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 md:p-6 shadow-sm">
      {/* Header */}
      <div className="flex items-center space-x-2.5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
          <CloudRain className="h-5 w-5" />
        </div>
        <h2 className="text-lg font-bold text-slate-900">What are you observing?</h2>
      </div>

      {/* Grid of Category Buttons (2 columns mobile, 4 columns desktop) */}
      <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {CATEGORIES.map((cat) => {
          const Icon = cat.icon;
          const isSelected = selectedCategory === cat.code;

          return (
            <button
              key={cat.code}
              type="button"
              onClick={() => handleSelectCategory(cat.code)}
              className={`flex flex-col items-center justify-center rounded-xl p-4 text-center transition-all focus:outline-none focus:ring-2 focus:ring-blue-600/30 ${
                isSelected
                  ? 'border-2 border-blue-600 bg-blue-50/60 text-blue-900 shadow-sm'
                  : 'border border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50'
              }`}
            >
              <Icon
                className={`h-6 w-6 transition-colors ${
                  isSelected ? 'text-blue-600' : 'text-slate-500'
                }`}
              />
              <span className="mt-2 text-xs md:text-sm font-semibold">
                {cat.label}
              </span>
            </button>
          );
        })}
      </div>

      {errors.category_code && (
        <p className="mt-2 text-xs font-medium text-rose-600">
          {errors.category_code.message || 'Please select an observation category.'}
        </p>
      )}
    </div>
  );
};
