// Where Halo finds Seraph and the kit server. By default: the laptop that serves this app (Metro's host), so the
// phone reaches both over the LAN with no setup. Override with EXPO_PUBLIC_SERAPH_URL / EXPO_PUBLIC_KIT_URL.
import Constants from 'expo-constants';

const host = (Constants.expoConfig?.hostUri ?? 'localhost').split(':')[0];

export const SERAPH_URL = process.env.EXPO_PUBLIC_SERAPH_URL ?? `http://${host}:8000`;
export const KIT_URL = process.env.EXPO_PUBLIC_KIT_URL ?? `http://${host}:3001`;

// Until Silex serves Devin's views, a fallback://<moment> can show the kit example for that moment instead.
export const STANDIN_DEFAULT = process.env.EXPO_PUBLIC_HALO_STANDIN !== '0';
export const STANDIN_MOMENTS = ['approach', 'inside_route', 'occupants', 'team_engaged'];

export const VIEW_SILENT_MS = 5000;   // a view that never says seraph:ready → vue de secours
export const ALERT_MS = 8000;
