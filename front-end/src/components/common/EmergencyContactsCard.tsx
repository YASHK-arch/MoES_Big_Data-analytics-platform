import React from 'react';
import { PhoneCall, ShieldAlert, Building, Radio, Droplets } from 'lucide-react';

interface ContactItem {
  name: string;
  agency: string;
  phone: string;
  icon: React.ReactNode;
  bgClass: string;
  borderClass: string;
  badge: string;
}

export const EmergencyContactsCard: React.FC = () => {
  const contacts: ContactItem[] = [
    {
      name: 'NDRF National Helpline',
      agency: 'National Disaster Response Force',
      phone: '1078',
      icon: <ShieldAlert className="h-5 w-5 text-rose-600" />,
      bgClass: 'bg-rose-50/80',
      borderClass: 'border-rose-200',
      badge: '24x7 SOS',
    },
    {
      name: 'State Disaster Emergency (SDRF)',
      agency: 'State Control Room',
      phone: '1070',
      icon: <Building className="h-5 w-5 text-amber-600" />,
      bgClass: 'bg-amber-50/80',
      borderClass: 'border-amber-200',
      badge: 'State Control',
    },
    {
      name: 'District Emergency Ops (DEOC)',
      agency: 'District Collectorate Helpline',
      phone: '1077',
      icon: <Radio className="h-5 w-5 text-blue-600" />,
      bgClass: 'bg-blue-50/80',
      borderClass: 'border-blue-200',
      badge: 'Local DEOC',
    },
    {
      name: 'CWC Flood Control Helpline',
      agency: 'Central Water Commission',
      phone: '1800-11-2020',
      icon: <Droplets className="h-5 w-5 text-cyan-600" />,
      bgClass: 'bg-cyan-50/80',
      borderClass: 'border-cyan-200',
      badge: 'River Telemetry',
    },
  ];

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-extrabold text-slate-900 flex items-center space-x-2">
            <PhoneCall className="h-4 w-4 text-rose-600" />
            <span>Emergency Quick-Dial Directory</span>
          </h3>
          <p className="text-[11px] text-slate-500 mt-0.5">
            One-tap direct dial to NDRF, SDRF, DEOC, and CWC flood control helplines
          </p>
        </div>
        <span className="text-[10px] font-extrabold uppercase tracking-wider bg-rose-50 text-rose-700 border border-rose-200 px-2.5 py-0.5 rounded-full">
          Verified Helplines
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {contacts.map((c) => (
          <a
            key={c.phone}
            href={`tel:${c.phone}`}
            className={`flex items-start justify-between p-3.5 rounded-xl border ${c.borderClass} ${c.bgClass} hover:shadow-md transition-all group`}
          >
            <div className="space-y-1">
              <div className="flex items-center space-x-2">
                {c.icon}
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-600">{c.badge}</span>
              </div>
              <h4 className="text-xs font-bold text-slate-900 group-hover:text-blue-700 transition-colors line-clamp-1">
                {c.name}
              </h4>
              <p className="text-[10px] text-slate-500">{c.agency}</p>
            </div>
            <div className="shrink-0 text-right">
              <span className="inline-flex items-center space-x-1 font-mono font-extrabold text-xs text-slate-900 bg-white px-2 py-1 rounded-lg border border-slate-200 shadow-2xs group-hover:border-blue-400 group-hover:text-blue-700 transition-colors">
                <span>{c.phone}</span>
              </span>
            </div>
          </a>
        ))}
      </div>
    </div>
  );
};
