/**
 * Geographic constants and spatial coordinate defaults for India.
 */

export const INDIA_CENTROID: [number, number] = [20.5937, 78.9629];
export const DEFAULT_MAP_ZOOM = 5;
export const DEFAULT_LOCAL_RADIUS_KM = 25.0;

export const POPULAR_CITIES = [
  { name: 'Mumbai', state: 'Maharashtra', lat: 19.076, lon: 72.8777 },
  { name: 'Delhi / NCR', state: 'Delhi', lat: 28.6139, lon: 77.209 },
  { name: 'Bengaluru', state: 'Karnataka', lat: 12.9716, lon: 77.5946 },
  { name: 'Chennai', state: 'Tamil Nadu', lat: 13.0827, lon: 80.2707 },
  { name: 'Kolkata', state: 'West Bengal', lat: 22.5726, lon: 88.3639 },
  { name: 'Hyderabad', state: 'Telangana', lat: 17.385, lon: 78.4867 },
  { name: 'Pune', state: 'Maharashtra', lat: 18.5204, lon: 73.8567 },
  { name: 'Jaipur', state: 'Rajasthan', lat: 26.9124, lon: 75.7873 },
  { name: 'Ahmedabad', state: 'Gujarat', lat: 23.0225, lon: 72.5714 },
  { name: 'Guwahati', state: 'Assam', lat: 26.1445, lon: 91.7362 },
  { name: 'Kochi', state: 'Kerala', lat: 9.9312, lon: 76.2673 },
  { name: 'Bhubaneswar', state: 'Odisha', lat: 20.2961, lon: 85.8245 },
] as const;
