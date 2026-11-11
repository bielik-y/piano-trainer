import { router } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';
import Animated, { FadeInUp } from 'react-native-reanimated';

import { ErrorBadge, PlayButton, Press, ProgressBar, Tag } from '@/components/ui/controls';
import { Glass } from '@/components/ui/glass';
import { Orb } from '@/components/ui/orb';
import { colors, fonts, radius, type } from '@/theme/tokens';

import type { LibraryCard } from './queries';
import { measuresText, pl } from './text';

/** Карточка библиотеки (LightMain): сфера 100 + тег, название, автор и строка состояния. */
export function PieceCard({ card }: { card: LibraryCard }) {
  const ready = card.status !== 'digitizing' && card.status !== 'failed';
  const errLabel = `${card.errorCount} ${pl(card.errorCount, 'такт', 'такта', 'тактов')} с ошибками распознавания`;

  return (
    <Animated.View entering={FadeInUp.duration(500)}>
      <Glass radius={radius.card} contentStyle={styles.card}>
        <Orb hue={card.hue} size={100} plate muted={card.status === 'failed'}>
          {ready ? <PlayButton label={`Прослушать: ${card.title}`} /> : null}
        </Orb>
        <Press
          accessibilityRole="button"
          disabled={!card.route}
          onPress={() => router.push({ pathname: '/piece/[id]', params: { id: card.route } })}
          scale={0.98}
          style={styles.body}
        >
          {card.status ? <Tag status={card.status} /> : null}
          <Text style={styles.title} numberOfLines={2}>
            {card.title}
          </Text>
          <Text style={styles.composer} numberOfLines={1}>
            {card.composer}
          </Text>
          {ready ? (
            <View style={styles.meta}>
              <Text style={styles.metaText}>{measuresText(card.measureCount)}</Text>
              {card.errorCount > 0 ? <ErrorBadge count={card.errorCount} label={errLabel} /> : null}
            </View>
          ) : null}
          {card.progress ? (
            <View style={styles.prog}>
              <ProgressBar fraction={card.progress.fraction} />
              <Text style={styles.ptext}>{card.progress.text}</Text>
            </View>
          ) : null}
          {card.failShort ? <Text style={styles.fail}>{card.failShort}</Text> : null}
        </Press>
      </Glass>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  card: { flexDirection: 'row', gap: 14, padding: 10 },
  body: { flex: 1, justifyContent: 'center', gap: 3, paddingVertical: 4, paddingRight: 6 },
  title: { ...type.cardTitle, color: colors.ink, marginTop: 4 },
  composer: { ...type.secondary, color: colors.ink2 },
  meta: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 6 },
  metaText: { fontFamily: fonts.bold, fontSize: 12, color: colors.ink3 },
  prog: { marginTop: 8, alignSelf: 'stretch' },
  ptext: { marginTop: 7, ...type.small, color: colors.ink2 },
  fail: { marginTop: 4, fontFamily: fonts.bold, fontSize: 12, color: colors.redInk },
});
