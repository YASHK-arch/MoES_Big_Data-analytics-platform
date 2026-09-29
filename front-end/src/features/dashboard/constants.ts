export interface RegionInfo {
  label: string;
  center: [number, number];
  zoom: number;
  bbox?: string;
}

export const REGIONS: Record<string, RegionInfo> = {
  ALL: { label: 'All India', center: [20.5937, 78.9629], zoom: 5 },
  MH: { label: 'Maharashtra', center: [19.7515, 75.7139], zoom: 7, bbox: '72.6,15.6,80.9,22.0' },
  TN: { label: 'Tamil Nadu', center: [11.1271, 78.6569], zoom: 7, bbox: '76.2,8.0,80.3,13.5' },
  DL: { label: 'Delhi-NCR', center: [28.7041, 77.1025], zoom: 10, bbox: '76.8,28.4,77.4,28.9' },
  KA: { label: 'Karnataka', center: [15.3173, 75.7139], zoom: 7, bbox: '74.0,11.5,78.6,18.5' },
  KL: { label: 'Kerala', center: [10.8505, 76.2711], zoom: 7, bbox: '74.8,8.3,77.4,12.8' },
  AS: { label: 'Assam', center: [26.2006, 92.9376], zoom: 7, bbox: '89.7,24.1,96.0,28.2' },
  RJ: { label: 'Rajasthan', center: [27.0238, 74.2179], zoom: 6, bbox: '69.5,23.0,78.3,30.2' },
};

export const HAZARDS = [
  { code: 'ALL', label: 'All Events' },
  { code: 'HEAVY_RAINFALL', label: 'Heavy Rainfall' },
  { code: 'FLOOD_WATERLOGGING', label: 'Flooding & Waterlogging' },
  { code: 'CYCLONE_STORM', label: 'Cyclone & Storm' },
  { code: 'THUNDERSTORM_LIGHTNING', label: 'Thunderstorm & Lightning' },
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

export const STATUSES = [
  { code: 'ALL', label: 'All Statuses' },
  { code: 'VERIFIED', label: 'Verified Only' },
  { code: 'PENDING', label: 'Pending Review' },
  { code: 'UNDER_REVIEW', label: 'Under Review' },
  { code: 'REJECTED', label: 'Rejected' },
];
