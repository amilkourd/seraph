// Halo: phone A on the forearm, landscape, full screen. Shows the view Silex built for this moment, fed live from
// Seraph; the vue de secours when there is none; alerts over everything. Brief: briefs/halo.md.
import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { useKeepAwake } from 'expo-keep-awake';
import * as ScreenOrientation from 'expo-screen-orientation';
import { KIT_URL, STANDIN_DEFAULT, STANDIN_MOMENTS } from './src/config';
import { useSeraph } from './src/seraph';
import { ViewHost, ViewStatus } from './src/ViewHost';
import { Fallback } from './src/Fallback';
import { AlertBanner, AlertList, useAlerts } from './src/Alerts';
import { C, FONT, Tag } from './src/ui';

const hhmm = (d: Date) => `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;

export default function App() {
  useKeepAwake();
  useEffect(() => { ScreenOrientation.lockAsync(ScreenOrientation.OrientationLock.LANDSCAPE); }, []);

  const alerts = useAlerts();
  const { state, view, online } = useSeraph(alerts.push);
  const [standin, setStandin] = useState(STANDIN_DEFAULT);
  const [status, setStatus] = useState<ViewStatus>('loading');
  const [showList, setShowList] = useState(false);
  const [now, setNow] = useState(new Date());
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 5000); return () => clearInterval(t); }, []);

  // what to load: Devin's view, or (until Silex runs) the kit example for this moment
  const moment = view?.moment ?? 'dispatch';
  const fallback = !view || view.url.startsWith('fallback://');
  const example = fallback && standin && STANDIN_MOMENTS.includes(moment);
  const url = !fallback ? view!.url : example ? `${KIT_URL}/views/${moment}/` : null;
  // the vue de secours only when there is no view or it failed: never flashed while a view loads
  const secours = !url || status === 'failed';

  // the building's provenance, short: the full sentence is on the dashboard
  const PROV: Record<string, string> = { architect: 'IFC réel', rebuilt_from_posted_plan: 'IFC reconstruit', fictional: 'bâtiment fictif' };
  const provenance = PROV[state?.building?.model?.provenance] ?? 'bâtiment fictif';
  const since = state?.halo?.current_view?.since;
  const line = secours ? 'Vue de secours' : example ? 'Exemple' : `Devin ${since ? hhmm(new Date(since)) : ''}`;

  return (
    <View style={s.root}>
      <StatusBar hidden />
      {secours && <Fallback moment={moment} state={state} />}
      {url && <ViewHost url={url} state={state} onStatus={setStatus} />}

      {/* top bar: EXERCICE · clock · connection */}
      <Pressable style={s.top} onPress={() => setShowList(true)}>
        {state?.incident?.exercise !== false && <Tag text="Exercice" tone="warn" />}
        <Tag text={hhmm(now)} />
        <View style={[s.dot, { backgroundColor: online ? C.ink : 'transparent', borderColor: online ? C.ink : C.fire }]} />
      </Pressable>

      {/* status line: who built this view, and where the building comes from. Long press: kit examples on/off */}
      <Pressable style={s.status} onLongPress={() => setStandin(v => !v)}>
        <Tag text={`${line} · ${provenance}`} tone="dim" size={18} />
      </Pressable>

      <AlertBanner alert={alerts.shown} onPress={() => { alerts.dismiss(); setShowList(true); }} />
      {showList && <AlertList list={alerts.list} onClose={() => setShowList(false)} />}
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg },
  top: { position: 'absolute', top: 10, right: 18, flexDirection: 'row', alignItems: 'center', gap: 6 },
  dot: { width: 14, height: 14, borderRadius: 7, borderWidth: 2, marginLeft: 4 },
  status: { position: 'absolute', bottom: 8, right: 18 },
});
