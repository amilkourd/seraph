// Hosts the view Silex built for this moment in a WebView, fed live. Contract: contracts/halo-views.md.
// The view fades in over the vue de secours once it says seraph:ready; silent for 5 s or failing → stays on secours.
import { useEffect, useRef, useState } from 'react';
import { Animated, StyleSheet } from 'react-native';
import RNWebView, { WebViewMessageEvent } from 'react-native-webview';
import * as Haptics from 'expo-haptics';
import { VIEW_SILENT_MS } from './config';
import { State, tap } from './seraph';

// react-native-webview 14's class types don't line up with React 19's JSX types yet
const WebView = RNWebView as any;

export type ViewStatus = 'loading' | 'ready' | 'failed';

export function ViewHost({ url, state, onStatus }: { url: string; state: State | null; onStatus: (s: ViewStatus) => void }) {
  const web = useRef<RNWebView>(null);
  const fade = useRef(new Animated.Value(0)).current;
  const [ready, setReady] = useState(false);
  const loaded = useRef(false);

  // a new url = a new view: hidden until it is ready
  useEffect(() => {
    fade.setValue(0); setReady(false); loaded.current = false; onStatus('loading');
    const t = setTimeout(() => { if (!loaded.current) onStatus('failed'); }, VIEW_SILENT_MS);
    return () => clearTimeout(t);
  }, [url]);

  // push the state on every change, not on every render
  useEffect(() => { if (state) send(state); }, [state]);

  function send(st: State) {
    web.current?.postMessage(JSON.stringify({ type: 'seraph:state', state: st }));
  }

  function onMessage(e: WebViewMessageEvent) {
    let m: any;
    try { m = JSON.parse(e.nativeEvent.data); } catch { return; }
    if (m?.type === 'seraph:ready' && !ready) {
      loaded.current = true; setReady(true); onStatus('ready');
      if (state) send(state);
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      Animated.timing(fade, { toValue: 1, duration: 300, useNativeDriver: true }).start();
    } else if (m?.type === 'seraph:error') {
      console.warn(`halo view error: ${m.message} @${m.line}:${m.col}`);
    } else if (m?.type === 'seraph:tap' && m.target) {
      tap(m.target);
    }
  }

  return (
    <Animated.View style={[StyleSheet.absoluteFill, { opacity: fade }]} pointerEvents={ready ? 'auto' : 'none'}>
      <WebView
        key={url}
        ref={web}
        source={{ uri: url }}
        style={{ flex: 1, backgroundColor: '#000' }}
        originWhitelist={['*']}
        onMessage={onMessage}
        onLoadEnd={() => { if (state) send(state); }}
        onError={() => onStatus('failed')}
        onHttpError={() => onStatus('failed')}
        scrollEnabled={false}
        bounces={false}
        contentInsetAdjustmentBehavior="never"
        automaticallyAdjustContentInsets={false}
        allowsInlineMediaPlayback
        setSupportMultipleWindows={false}
      />
    </Animated.View>
  );
}
