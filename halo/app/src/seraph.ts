// Seraph's live feed for Halo: SSE /stream?client=halo (state, alert, halo_view), taps to POST /halo/tap.
import { useEffect, useRef, useState } from 'react';
import EventSource from 'react-native-sse';
import { SERAPH_URL } from './config';

export type Source = { kind: string; label: string; confirmed: boolean };
export type Alert = { alert_id: string; level: 'info' | 'warning' | 'danger'; text_fr: string; created_at: string };
export type HaloView = { view_id: string; url: string; moment: string; built_by: 'devin' | 'fallback' };
export type State = any;   // IncidentState (contracts/types.ts); read defensively

type Events = 'state' | 'alert' | 'halo_view';

export function useSeraph(onAlert: (a: Alert) => void) {
  const [state, setState] = useState<State | null>(null);
  const [view, setView] = useState<HaloView | null>(null);
  const [online, setOnline] = useState(false);
  const alertRef = useRef(onAlert);
  alertRef.current = onAlert;

  useEffect(() => {
    const es = new EventSource<Events>(`${SERAPH_URL}/stream?client=halo`, { pollingInterval: 2000 });
    es.addEventListener('open', () => setOnline(true));
    es.addEventListener('error', () => setOnline(false));
    es.addEventListener('state', e => { if (e.data) setState(JSON.parse(e.data)); });
    es.addEventListener('halo_view', e => { if (e.data) setView(JSON.parse(e.data)); });
    es.addEventListener('alert', e => { if (e.data) alertRef.current(JSON.parse(e.data)); });
    return () => { es.removeAllEventListeners(); es.close(); };
  }, []);

  // the current view is also in the state; use it until a halo_view event arrives
  const current: HaloView | null = view ?? state?.halo?.current_view ?? null;
  return { state, view: current, online };
}

export function tap(target: { kind: string; id: string }) {
  fetch(`${SERAPH_URL}/halo/tap`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(target) })
    .catch(() => { /* offline: the tap is lost, Seraph shows nothing */ });
}
