import type { OmrJob, Piece } from '@piano/contracts';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { BackIcon, CheckIcon, EditIcon, MoreIcon, TrashIcon } from '@/components/icons';
import {
  IconButton,
  InkButton,
  PlayButton,
  Press,
  ProgressBar,
  Tag,
} from '@/components/ui/controls';
import { Background, Glass } from '@/components/ui/glass';
import { Orb } from '@/components/ui/orb';
import { Sheet } from '@/components/ui/sheet';
import { useToast } from '@/components/ui/toast';
import { requestErrorText } from '@/features/library/errors';
import { measureIssueText } from '@/features/library/measure-issues';
import {
  jobCard,
  useDeletePiece,
  useDismissJob,
  useInbox,
  useMarkOpened,
  usePieces,
  useRenamePiece,
} from '@/features/library/queries';
import { failureText, jobProgress, jobTitle, meterSubtitle, pl } from '@/features/library/text';
import { orbColors } from '@/theme/orb';
import { colors, fonts, radius, type } from '@/theme/tokens';

/** Страница произведения (артборд LightPiece). id — пьеса или job:<id> — задача распознавания. */
export default function PieceScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const pieces = usePieces();
  const inbox = useInbox();

  const jobId = id.startsWith('job:') ? id.slice(4) : null;
  const job = jobId ? inbox.data?.find((j) => j.id === jobId) : undefined;
  // Задача могла распознаться, пока страница открыта: тогда показываем пьесу из неё.
  const piece = jobId
    ? pieces.data?.find((p) => p.omrJobId === jobId)
    : pieces.data?.find((p) => p.id === id);

  if (piece) return <PieceView piece={piece} />;
  if (job) return <JobView job={job} />;
  return (
    <Shell hue={210}>
      {pieces.isPending || inbox.isPending ? (
        <ActivityIndicator color={colors.ink3} style={{ marginTop: 80 }} />
      ) : (
        <Text style={[styles.note, { textAlign: 'center', marginTop: 80 }]}>
          Произведение не найдено — возможно, оно удалено.
        </Text>
      )}
    </Shell>
  );
}

/** Каркас страницы: фон, тонированный цветом сферы, кнопки «Назад» и «Ещё». */
function Shell({
  hue,
  muted,
  onMore,
  children,
}: {
  hue: number;
  muted?: boolean;
  onMore?: () => void;
  children: React.ReactNode;
}) {
  const insets = useSafeAreaInsets();
  return (
    <View style={{ flex: 1 }}>
      <Background tint={orbColors(hue, muted).halo} />
      <ScrollView
        contentContainerStyle={{
          paddingTop: insets.top + 8,
          paddingBottom: insets.bottom + 48,
          paddingHorizontal: 16,
        }}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.topbar}>
          <IconButton label="Назад" onPress={() => router.back()}>
            <BackIcon size={20} />
          </IconButton>
          {onMore ? (
            <IconButton label="Ещё" onPress={onMore}>
              <MoreIcon />
            </IconButton>
          ) : null}
        </View>
        {children}
      </ScrollView>
    </View>
  );
}

function Hero({
  hue,
  status,
  title,
  composer,
  canPlay,
}: {
  hue: number;
  status: 'new' | 'digitizing' | 'failed' | null;
  title: string;
  composer: string;
  canPlay: boolean;
}) {
  return (
    <View style={styles.hero}>
      <Orb
        hue={hue}
        size={250}
        muted={status === 'failed'}
        style={{ marginTop: -6, marginBottom: 4 }}
      >
        {canPlay ? <PlayButton size={68} label={`Прослушать: ${title}`} /> : null}
      </Orb>
      {status ? <Tag status={status} /> : null}
      <Text style={styles.ptitle}>{title}</Text>
      <Text style={styles.pcomposer}>{composer}</Text>
    </View>
  );
}

function PieceView({ piece }: { piece: Piece }) {
  const toast = useToast();
  const markOpened = useMarkOpened();
  const remove = useDeletePiece();
  const [menu, setMenu] = useState(false);
  const [renaming, setRenaming] = useState(false);
  // «Новое» видно на этом открытии, а на сервере сразу отмечаем, что пьесу открыли.
  const [wasNew] = useState(piece.openedAt === null);
  const marked = useRef(false);

  useEffect(() => {
    if (piece.openedAt === null && !marked.current) {
      marked.current = true;
      markOpened.mutate(piece.id);
    }
  }, [piece.id, piece.openedAt, markOpened]);

  const errors = piece.suspiciousMeasures.map((m) => measureIssueText(piece, m));
  const ec = errors.length;
  const meterSub = meterSubtitle(piece);

  const confirmDelete = () => {
    setMenu(false);
    Alert.alert('Удалить произведение?', `«${piece.title}» пропадёт из библиотеки.`, [
      { text: 'Отмена', style: 'cancel' },
      {
        text: 'Удалить',
        style: 'destructive',
        onPress: () =>
          remove.mutate(piece.id, {
            onSuccess: () => router.back(),
            onError: (e) => toast(requestErrorText(e)),
          }),
      },
    ]);
  };

  return (
    <>
      <Shell hue={piece.hue} onMore={() => setMenu(true)}>
        <Hero
          hue={piece.hue}
          status={wasNew ? 'new' : null}
          title={piece.title}
          composer={piece.composer ?? 'Автор не указан'}
          canPlay
        />
        <View style={styles.stats}>
          <Stat label="Тактов" value={String(piece.measureCount)} />
          <Stat label="Размер" value={piece.timeSignature ?? '—'} sub={meterSub} />
          <Stat
            label="Темп"
            value={piece.tempoBpm ? `♩ = ${piece.tempoBpm}` : (piece.tempoText ?? 'Не указан')}
            dim={!piece.tempoBpm && !piece.tempoText}
          />
          <Stat label="С ошибками" value={String(ec)} bad={ec > 0} />
        </View>

        <View style={styles.sect}>
          {ec > 0 ? (
            <>
              <Text style={styles.h3}>Ошибки распознавания</Text>
              <Text style={styles.note}>
                {ec} {pl(ec, 'такт', 'такта', 'тактов')} с ошибками. Они помечены на нотах и не
                учитываются при проверке игры.
              </Text>
              <View style={{ gap: 10 }}>
                {errors.map((e, i) => (
                  <View key={`${e.measure}-${i}`} style={styles.erow}>
                    <View style={styles.mbadge}>
                      <Text style={styles.mbadgeSmall}>такт</Text>
                      <Text style={styles.mbadgeNum}>{e.measure}</Text>
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.etitle}>{e.title}</Text>
                      <Text style={styles.edetail}>{e.detail}</Text>
                    </View>
                    <InkButton
                      label="Изменить"
                      icon={<EditIcon size={15} color="#fff" />}
                      onPress={() => toast('Редактор тактов появится в следующей версии')}
                      style={{ paddingHorizontal: 14 }}
                    />
                  </View>
                ))}
              </View>
            </>
          ) : (
            <View style={styles.okcard}>
              <View style={styles.okdot}>
                <CheckIcon size={16} color="#fff" />
              </View>
              <Text style={[styles.cardText, { flex: 1 }]}>
                Ошибок распознавания нет: все такты прошли проверку.
              </Text>
            </View>
          )}
        </View>
      </Shell>

      <Sheet open={menu} onClose={() => setMenu(false)} label="Действия с произведением">
        <MenuItem
          icon={<EditIcon size={20} />}
          label="Переименовать"
          onPress={() => {
            setMenu(false);
            setRenaming(true);
          }}
        />
        <MenuItem
          icon={<TrashIcon size={20} color={colors.red} />}
          label="Удалить"
          danger
          onPress={confirmDelete}
        />
      </Sheet>
      <RenameSheet piece={piece} open={renaming} onClose={() => setRenaming(false)} />
    </>
  );
}

function JobView({ job }: { job: OmrJob }) {
  const toast = useToast();
  const dismiss = useDismissJob();
  const failed = job.status === 'failed';
  const card = jobCard(job);
  const progress = jobProgress(job);
  const failure = failureText(job.error?.code);

  return (
    <Shell hue={job.hue} muted={failed}>
      <Hero
        hue={job.hue}
        status={failed ? 'failed' : 'digitizing'}
        title={jobTitle(job)}
        composer={card.composer}
        canPlay={false}
      />
      <View style={styles.sect}>
        {failed ? (
          <View style={[styles.infocard, styles.infocardBad]}>
            <Text style={styles.cardText}>{failure.short}</Text>
            <Text style={styles.ssub}>{failure.long}</Text>
            <InkButton
              label="Убрать из библиотеки"
              disabled={dismiss.isPending}
              onPress={() =>
                dismiss.mutate(job.id, {
                  onSuccess: () => router.back(),
                  onError: (e) => toast(requestErrorText(e)),
                })
              }
              style={{ marginTop: 6 }}
            />
          </View>
        ) : (
          <View style={styles.infocard}>
            <Text style={styles.cardText}>{progress.text}</Text>
            <ProgressBar fraction={progress.fraction} />
            <Text style={styles.ssub}>
              Название, автор, размер и темп появятся после распознавания.
            </Text>
          </View>
        )}
      </View>
    </Shell>
  );
}

function Stat({
  label,
  value,
  sub,
  dim,
  bad,
}: {
  label: string;
  value: string;
  sub?: string | null;
  dim?: boolean;
  bad?: boolean;
}) {
  return (
    <Glass
      radius={radius.tile}
      from={0.85}
      to={0.55}
      blur={20}
      style={[styles.statBox, bad && styles.statBad]}
      contentStyle={styles.stat}
    >
      <Text style={styles.slabel}>{label}</Text>
      <Text style={[styles.sval, dim && styles.svalDim, bad && { color: '#C8283B' }]}>{value}</Text>
      {sub ? <Text style={styles.ssub}>{sub}</Text> : null}
    </Glass>
  );
}

function MenuItem({
  icon,
  label,
  danger,
  onPress,
}: {
  icon: React.ReactNode;
  label: string;
  danger?: boolean;
  onPress: () => void;
}) {
  return (
    <Press accessibilityRole="button" onPress={onPress} scale={0.98} style={styles.menuItem}>
      {icon}
      <Text style={[styles.menuText, danger && { color: colors.redInk }]}>{label}</Text>
    </Press>
  );
}

function RenameSheet({
  piece,
  open,
  onClose,
}: {
  piece: Piece;
  open: boolean;
  onClose: () => void;
}) {
  const toast = useToast();
  const rename = useRenamePiece();
  const [title, setTitle] = useState(piece.title);
  const [composer, setComposer] = useState(piece.composer ?? '');

  // При каждом открытии — актуальные значения.
  const [lastOpen, setLastOpen] = useState(open);
  if (open !== lastOpen) {
    setLastOpen(open);
    if (open) {
      setTitle(piece.title);
      setComposer(piece.composer ?? '');
    }
  }

  const save = () =>
    rename.mutate(
      { id: piece.id, body: { title: title.trim(), composer: composer.trim() || null } },
      { onSuccess: onClose, onError: (e) => toast(requestErrorText(e)) },
    );

  return (
    <Sheet open={open} onClose={onClose} label="Переименовать">
      <Text style={styles.sheetTitle}>Переименовать</Text>
      <Text style={styles.flabel}>Название</Text>
      <TextInput
        value={title}
        onChangeText={setTitle}
        style={styles.input}
        maxLength={200}
        placeholder="Название произведения"
        placeholderTextColor={colors.ink3}
        returnKeyType="next"
      />
      <Text style={styles.flabel}>Автор</Text>
      <TextInput
        value={composer}
        onChangeText={setComposer}
        style={styles.input}
        maxLength={200}
        placeholder="Не указан"
        placeholderTextColor={colors.ink3}
        returnKeyType="done"
        onSubmitEditing={save}
      />
      <InkButton
        label="Сохранить"
        disabled={!title.trim() || rename.isPending}
        onPress={save}
        style={{ marginTop: 18 }}
      />
    </Sheet>
  );
}

const styles = StyleSheet.create({
  topbar: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  hero: { alignItems: 'center' },
  ptitle: {
    ...type.pageTitle,
    color: colors.ink,
    textAlign: 'center',
    marginTop: 6,
    maxWidth: 330,
  },
  pcomposer: {
    fontFamily: fonts.medium,
    fontSize: 15,
    color: colors.ink2,
    marginTop: 6,
    textAlign: 'center',
  },
  stats: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 24 },
  statBox: { width: '48.5%', flexGrow: 1 },
  statBad: { borderColor: 'rgba(229,57,76,0.2)' },
  stat: { paddingVertical: 14, paddingHorizontal: 16, gap: 4 },
  slabel: {
    fontFamily: fonts.bold,
    fontSize: 11,
    letterSpacing: 0.88,
    textTransform: 'uppercase',
    color: colors.ink3,
  },
  sval: { fontFamily: fonts.extrabold, fontSize: 22, letterSpacing: -0.2, color: colors.ink },
  svalDim: { fontFamily: fonts.semibold, fontSize: 16, color: colors.ink2, paddingVertical: 3 },
  ssub: { fontFamily: fonts.medium, fontSize: 12, color: colors.ink2 },
  sect: { marginTop: 28 },
  h3: { ...type.section, color: colors.ink },
  note: { ...type.secondary, color: colors.ink2, marginTop: 6, marginBottom: 14 },
  erow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    padding: 10,
    borderRadius: 22,
    backgroundColor: 'rgba(255,255,255,0.7)',
    borderWidth: 1,
    borderColor: '#fff',
  },
  mbadge: {
    width: 52,
    height: 52,
    borderRadius: 16,
    backgroundColor: 'rgba(229,57,76,0.09)',
    borderWidth: 1,
    borderColor: 'rgba(229,57,76,0.25)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  mbadgeSmall: {
    fontFamily: fonts.bold,
    fontSize: 9,
    letterSpacing: 0.72,
    textTransform: 'uppercase',
    color: colors.redInk,
  },
  mbadgeNum: { fontFamily: fonts.extrabold, fontSize: 19, lineHeight: 21, color: colors.redDeep },
  etitle: { fontFamily: fonts.bold, fontSize: 14, lineHeight: 18, color: colors.ink },
  edetail: {
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 16,
    color: colors.ink2,
    marginTop: 3,
  },
  okcard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    padding: 16,
    borderRadius: 22,
    backgroundColor: 'rgba(47,107,255,0.07)',
    borderWidth: 1,
    borderColor: 'rgba(47,107,255,0.2)',
  },
  okdot: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.blue,
    alignItems: 'center',
    justifyContent: 'center',
  },
  infocard: {
    gap: 10,
    padding: 16,
    borderRadius: 22,
    backgroundColor: 'rgba(47,107,255,0.07)',
    borderWidth: 1,
    borderColor: 'rgba(47,107,255,0.2)',
  },
  infocardBad: { backgroundColor: 'rgba(229,57,76,0.07)', borderColor: 'rgba(229,57,76,0.25)' },
  cardText: { ...type.body, color: colors.ink },
  menuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    height: 56,
    paddingHorizontal: 16,
    marginBottom: 8,
    borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.75)',
    borderWidth: 1,
    borderColor: 'rgba(15,25,50,0.06)',
  },
  menuText: { fontFamily: fonts.bold, fontSize: 16, color: colors.ink },
  sheetTitle: {
    fontFamily: fonts.extrabold,
    fontSize: 22,
    letterSpacing: -0.4,
    color: colors.ink,
    marginBottom: 8,
  },
  flabel: {
    fontFamily: fonts.bold,
    fontSize: 12,
    letterSpacing: 0.96,
    textTransform: 'uppercase',
    color: colors.ink3,
    marginTop: 14,
    marginBottom: 8,
  },
  input: {
    height: 50,
    paddingHorizontal: 16,
    borderRadius: 16,
    backgroundColor: 'rgba(255,255,255,0.85)',
    borderWidth: 1,
    borderColor: 'rgba(15,25,50,0.1)',
    fontFamily: fonts.semibold,
    fontSize: 16,
    color: colors.ink,
  },
});
