export interface RegionOption {
  label: string;
  bbox?: string;
  keywords?: string[];
}

export const TIME_RANGE_OPTIONS = [
  { code: '7d', label: 'Last 7 Days' },
  { code: '24h', label: 'Last 24 Hours' },
  { code: '30d', label: 'Last 30 Days' },
  { code: 'all', label: 'All Time' },
];

export const HAZARD_OPTIONS = [
  { code: 'ALL', label: 'All Events' },
  { code: 'HEAVY_RAINFALL', label: 'Heavy Rainfall' },
  { code: 'FLOOD_WATERLOGGING', label: 'Flooding & Waterlogging' },
  { code: 'THUNDERSTORM_LIGHTNING', label: 'Thunderstorm' },
  { code: 'CYCLONE_STORM', label: 'Strong Wind & Cyclone' },
  { code: 'HEATWAVE', label: 'Heatwave' },
  { code: 'HAILSTORM', label: 'Hailstorm' },
  { code: 'LANDSLIDE', label: 'Landslide' },
  { code: 'URBAN_FLOOD', label: 'Urban Inundation' },
  { code: 'DROUGHT', label: 'Drought' },
  { code: 'FOG', label: 'Dense Fog' },
  { code: 'DUST_STORM', label: 'Dust Storm' },
  { code: 'STRONG_WIND', label: 'Strong Wind' },
  { code: 'OTHER', label: 'Other Hazard' },
];

export const SEVERITY_OPTIONS = [
  { code: 'ALL', label: 'All Severities' },
  { code: 'SEVERE', label: 'Severe' },
  { code: 'HIGH', label: 'High' },
  { code: 'MODERATE', label: 'Moderate' },
  { code: 'LOW', label: 'Low' },
];

export const VERIFICATION_OPTIONS = [
  { code: 'ALL', label: 'All Verification Statuses' },
  { code: 'VERIFIED', label: 'Verified' },
  { code: 'PENDING', label: 'Pending' },
  { code: 'UNDER_REVIEW', label: 'Under Review' },
  { code: 'REJECTED', label: 'Rejected' },
  { code: 'DUPLICATE', label: 'Duplicate' },
];

export const GEOGRAPHY_OPTIONS: Record<string, RegionOption> = {
  ALL: { label: 'All India' },
  MH: {
    label: 'Maharashtra',
    bbox: '72.6,15.6,80.9,22.0',
    keywords: ['mumbai', 'pune', 'nagpur', 'thane', 'nashik', 'maharashtra', 'mh', 'kurla', 'andheri'],
  },
  TN: {
    label: 'Tamil Nadu',
    bbox: '76.2,8.0,80.3,13.5',
    keywords: ['chennai', 'coimbatore', 'madurai', 'tamil nadu', 'tn'],
  },
  DL: {
    label: 'Delhi NCR',
    bbox: '76.8,28.4,77.4,28.9',
    keywords: ['delhi', 'noida', 'gurgaon', 'new delhi', 'ncr', 'dl'],
  },
  KA: {
    label: 'Karnataka',
    bbox: '74.0,11.5,78.6,18.5',
    keywords: ['bengaluru', 'bangalore', 'mysore', 'karnataka', 'ka'],
  },
  KL: {
    label: 'Kerala',
    bbox: '74.8,8.3,77.4,12.8',
    keywords: ['kochi', 'thiruvananthapuram', 'calicut', 'kerala', 'kl'],
  },
  AS: {
    label: 'Assam',
    bbox: '89.7,24.1,96.0,28.2',
    keywords: ['guwahati', 'assam', 'as', 'dibrugarh', 'silchar'],
  },
  RJ: {
    label: 'Rajasthan',
    bbox: '69.5,23.0,78.3,30.2',
    keywords: ['jaipur', 'jodhpur', 'rajasthan', 'rj', 'udaipur'],
  },
};
