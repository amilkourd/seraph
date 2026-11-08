// Shared look: the kit's tokens (halo/kit/halo.css) and its black tag.
import { Text, View } from 'react-native';

export const C = {
  bg: '#000000', ink: '#ffffff', dim: '#8e8c87', panel: '#0a0a0a',
  fire: '#ff3d1f', warn: '#ffc61a', risk: '#ff8a24', water: '#3b8cff', life: '#2fe07a',
} as const;
export const FONT = 'Avenir Next';

export function Tag({ text, tone = 'ink', size = 20 }: { text: string; tone?: keyof typeof C; size?: number }) {
  return (
    <View style={{ backgroundColor: C.panel, paddingHorizontal: 8, paddingVertical: 4, alignSelf: 'flex-start' }}>
      <Text numberOfLines={1} style={{ color: C[tone], fontFamily: FONT, fontSize: size, fontWeight: '600', letterSpacing: 0.6 }}>
        {text.toUpperCase()}
      </Text>
    </View>
  );
}
