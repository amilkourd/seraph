// Alerts over everything: a banner for 8 s with haptics and a sound; all alerts in a list behind a tap.
import { useEffect, useRef, useState } from 'react';
import { Animated, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import * as Haptics from 'expo-haptics';
import { setAudioModeAsync, useAudioPlayer } from 'expo-audio';
import { ALERT_MS } from './config';
import { Alert } from './seraph';
import { C, FONT } from './ui';

const TONE = { info: C.ink, warning: C.warn, danger: C.fire } as const;

export function useAlerts() {
  const [list, setList] = useState<Alert[]>([]);
  const [shown, setShown] = useState<Alert | null>(null);
  const player = useAudioPlayer(require('../assets/alert.wav'));
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => { setAudioModeAsync({ playsInSilentMode: true, interruptionMode: 'duckOthers' }); }, []);

  function push(a: Alert) {
    setList(l => (l.some(x => x.alert_id === a.alert_id) ? l : [a, ...l]));
    setShown(a);
    Haptics.notificationAsync(a.level === 'danger' ? Haptics.NotificationFeedbackType.Error : Haptics.NotificationFeedbackType.Warning);
    player.seekTo(0); player.play();
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setShown(null), ALERT_MS);
  }
  return { list, shown, push, dismiss: () => setShown(null) };
}

export function AlertBanner({ alert, onPress }: { alert: Alert | null; onPress: () => void }) {
  const y = useRef(new Animated.Value(-120)).current;
  useEffect(() => { Animated.timing(y, { toValue: alert ? 0 : -120, duration: 220, useNativeDriver: true }).start(); }, [alert]);
  if (!alert) return null;
  return (
    <Animated.View style={[s.banner, { borderColor: TONE[alert.level], transform: [{ translateY: y }] }]}>
      <Pressable onPress={onPress}>
        <Text numberOfLines={2} style={[s.bannerText, { color: TONE[alert.level] }]}>{alert.text_fr.toUpperCase()}</Text>
      </Pressable>
    </Animated.View>
  );
}

export function AlertList({ list, onClose }: { list: Alert[]; onClose: () => void }) {
  return (
    <Pressable style={s.cover} onPress={onClose}>
      <ScrollView contentContainerStyle={s.list}>
        {list.length === 0 && <Text style={[s.row, { color: C.dim }]}>AUCUNE ALERTE</Text>}
        {list.map(a => (
          <Text key={a.alert_id} numberOfLines={1} style={[s.row, { color: TONE[a.level] }]}>{a.text_fr.toUpperCase()}</Text>
        ))}
      </ScrollView>
    </Pressable>
  );
}

const s = StyleSheet.create({
  banner: { position: 'absolute', top: 12, left: 64, right: 64, backgroundColor: '#0a0a0a', borderWidth: 3, paddingVertical: 14, paddingHorizontal: 18 },
  bannerText: { fontFamily: FONT, fontSize: 28, fontWeight: '800', letterSpacing: 0.5 },
  cover: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.94)' },
  list: { paddingHorizontal: 64, paddingVertical: 28, gap: 12 },
  row: { fontFamily: FONT, fontSize: 24, fontWeight: '700' },
});
