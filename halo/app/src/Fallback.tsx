// « Vue de secours »: what Halo shows while a view loads, when it fails, or when Seraph says fallback://<moment>.
// Native, so it works with no web view at all. Same look as the schemes: black, big plain lines, one line each.
// The status line says « Vue de secours »; no second label here.
import { StyleSheet, Text, View } from 'react-native';
import { factsFor, Line } from './facts';
import { State } from './seraph';
import { C, FONT } from './ui';

export function Fallback({ moment, state }: { moment: string; state: State | null }) {
  const lines = factsFor(moment, state);
  return (
    <View style={s.root}>
      <View style={s.lines}>
        {lines.map((l: Line, i) => (
          <Text key={i} numberOfLines={1} adjustsFontSizeToFit
            style={[s.line, l.big && s.big, { color: C[l.tone ?? 'ink'] }]}>{l.text.toUpperCase()}</Text>
        ))}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  root: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: C.bg, justifyContent: 'center', paddingHorizontal: 64 },
  lines: { gap: 10 },
  line: { fontFamily: FONT, fontSize: 34, fontWeight: '700', letterSpacing: 0.6 },
  big: { fontSize: 56, fontWeight: '800' },
});
