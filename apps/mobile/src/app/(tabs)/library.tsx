import { LinearGradient } from 'expo-linear-gradient';
import { ActivityIndicator, FlatList, RefreshControl, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { DOCK_SPACE } from '@/components/dock';
import { InkButton } from '@/components/ui/controls';
import { Background } from '@/components/ui/glass';
import { useOpenAddSheet } from '@/features/library/add-sheet';
import { requestErrorText } from '@/features/library/errors';
import { PieceCard } from '@/features/library/piece-card';
import { useLibrary } from '@/features/library/queries';
import { piecesCountText } from '@/features/library/text';
import { colors, type } from '@/theme/tokens';

/** Экран библиотеки (артборд LightMain). */
export default function LibraryScreen() {
  const insets = useSafeAreaInsets();
  const library = useLibrary();
  const openAddSheet = useOpenAddSheet();

  const header = (
    <View style={styles.head}>
      <View>
        <Text style={[type.eyebrow, { color: colors.ink3 }]}>Мой репертуар</Text>
        <Text style={styles.h1}>Библиотека</Text>
      </View>
      <Text style={styles.count}>{piecesCountText(library.pieceCount)}</Text>
    </View>
  );

  const empty = library.isLoading ? (
    <ActivityIndicator color={colors.ink3} style={{ marginTop: 40 }} />
  ) : library.error && !library.cards.length ? (
    <View style={styles.empty}>
      <Text style={styles.emptyTitle}>{requestErrorText(library.error)}</Text>
      <Text style={styles.emptyText}>
        Проверьте, что сервер запущен и телефон в той же сети, и потяните список вниз.
      </Text>
    </View>
  ) : (
    <View style={styles.empty}>
      <Text style={styles.emptyTitle}>Добавьте первое произведение</Text>
      <Text style={styles.emptyText}>
        Загрузите PDF с нотами или сфотографируйте страницы — мы распознаем их и добавим в
        библиотеку.
      </Text>
      <InkButton label="Добавить ноты" onPress={openAddSheet} style={{ marginTop: 16 }} />
    </View>
  );

  return (
    <View style={styles.root}>
      <Background />
      <FlatList
        data={library.cards}
        keyExtractor={(c) => c.key}
        renderItem={({ item }) => <PieceCard card={item} />}
        ItemSeparatorComponent={() => <View style={{ height: 12 }} />}
        ListHeaderComponent={header}
        ListEmptyComponent={empty}
        contentContainerStyle={[
          styles.list,
          { paddingTop: insets.top + 24, paddingBottom: DOCK_SPACE },
        ]}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={library.isRefetching}
            onRefresh={() => void library.refetch()}
            tintColor={colors.ink3}
          />
        }
      />
      <LinearGradient
        colors={[colors.bg, 'rgba(238,241,247,0)']}
        style={[styles.topfade, { height: insets.top + 8 }]}
        pointerEvents="none"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  list: { paddingHorizontal: 16 },
  head: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'space-between',
    paddingHorizontal: 4,
    paddingBottom: 22,
  },
  h1: { ...type.screenTitle, color: colors.ink, marginTop: 6 },
  count: { ...type.body, color: colors.ink2, paddingBottom: 6 },
  topfade: { position: 'absolute', left: 0, right: 0, top: 0 },
  empty: { alignItems: 'center', paddingHorizontal: 24, paddingTop: 48 },
  emptyTitle: { ...type.cardTitle, fontSize: 18, color: colors.ink, textAlign: 'center' },
  emptyText: { ...type.secondary, color: colors.ink2, textAlign: 'center', marginTop: 8 },
});
