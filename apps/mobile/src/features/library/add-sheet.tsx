import { OMR_LIMITS, TimeSignatureChoice } from '@piano/contracts';
import * as DocumentPicker from 'expo-document-picker';
import * as ImagePicker from 'expo-image-picker';
import { LinearGradient } from 'expo-linear-gradient';
import { createContext, useCallback, useContext, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Animated, { FadeIn, LinearTransition } from 'react-native-reanimated';

import {
  CameraIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  CloseIcon,
  FileIcon,
  GalleryIcon,
} from '@/components/icons';
import { Chip, IconButton, InkButton, Press } from '@/components/ui/controls';
import { Sheet } from '@/components/ui/sheet';
import { useToast } from '@/components/ui/toast';
import type { LocalFile } from '@/services/api/library';
import { colors, fonts } from '@/theme/tokens';

import { requestErrorText } from './errors';
import { useUpload } from './queries';
import { pl } from './text';

const AddSheetContext = createContext<() => void>(() => {});

/** Открыть шторку «Новое произведение» из любого экрана внутри табов. */
export function useOpenAddSheet() {
  return useContext(AddSheetContext);
}

export function AddSheetProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const show = useCallback(() => setOpen(true), []);
  return (
    <AddSheetContext.Provider value={show}>
      {children}
      <AddSheet open={open} onClose={() => setOpen(false)} />
    </AddSheetContext.Provider>
  );
}

const METERS = TimeSignatureChoice.options;
const MAX_MB = Math.round(OMR_LIMITS.maxFileBytes / 1024 / 1024);

const tooLarge = (files: LocalFile[]) =>
  files.some((f) => f.size !== undefined && f.size > OMR_LIMITS.maxFileBytes);

function imageFile(asset: ImagePicker.ImagePickerAsset, i: number): LocalFile {
  const type = asset.mimeType ?? 'image/jpeg';
  const ext = type.split('/')[1] ?? 'jpg';
  return {
    uri: asset.uri,
    name: asset.fileName ?? `page-${i + 1}.${ext}`,
    type,
    size: asset.fileSize,
  };
}

/** Шторка добавления (LightSheet): PDF, камера, галерея и размер такта в доп. настройках. */
function AddSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const toast = useToast();
  const upload = useUpload({ onError: (e) => toast(requestErrorText(e)) });
  const [adv, setAdv] = useState(false);
  const [meter, setMeter] = useState<TimeSignatureChoice>('auto');
  /** Снимки с камеры, пока пользователь снимает страницы по порядку. */
  const [shots, setShots] = useState<LocalFile[]>([]);

  const close = () => {
    setAdv(false);
    setShots([]);
    onClose();
  };

  const send = (files: LocalFile[]) => {
    if (!files.length) return;
    if (tooLarge(files)) {
      toast(`Файл больше ${MAX_MB} МБ`);
      return;
    }
    upload.mutate({ files, timeSignature: meter });
    close();
    setMeter('auto');
  };

  const pickFile = async () => {
    const res = await DocumentPicker.getDocumentAsync({
      type: 'application/pdf',
      copyToCacheDirectory: true,
    });
    if (res.canceled) return;
    const a = res.assets[0]!;
    send([{ uri: a.uri, name: a.name, type: a.mimeType ?? 'application/pdf', size: a.size }]);
  };

  const pickGallery = async () => {
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsMultipleSelection: true,
      selectionLimit: OMR_LIMITS.maxImages,
      orderedSelection: true,
      quality: 0.9,
    });
    if (res.canceled) return;
    send(res.assets.slice(0, OMR_LIMITS.maxImages).map(imageFile));
  };

  const shoot = async () => {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) {
      toast('Нет доступа к камере — разрешите его в настройках');
      return;
    }
    const res = await ImagePicker.launchCameraAsync({ mediaTypes: ['images'], quality: 0.9 });
    if (res.canceled) return;
    setShots((prev) => [...prev, imageFile(res.assets[0]!, prev.length)]);
  };

  const n = shots.length;
  return (
    <Sheet open={open} onClose={close} label="Добавить произведение">
      <View style={styles.head}>
        <View style={{ flex: 1 }}>
          <Text style={styles.h2}>Новое произведение</Text>
          <Text style={styles.sub}>PDF до 20 страниц или до 10 фото одного произведения</Text>
        </View>
        <IconButton label="Закрыть" onPress={close}>
          <CloseIcon size={18} />
        </IconButton>
      </View>

      {n > 0 ? (
        <Animated.View entering={FadeIn} style={styles.shots}>
          <Text style={styles.shotsText}>
            Снято {n} {pl(n, 'страница', 'страницы', 'страниц')} из {OMR_LIMITS.maxImages}
          </Text>
          <View style={styles.shotsRow}>
            {n < OMR_LIMITS.maxImages ? (
              <InkButton label="Ещё снимок" tone="plain" onPress={shoot} style={{ flex: 1 }} />
            ) : null}
            <InkButton label="Отправить" onPress={() => send(shots)} style={{ flex: 1 }} />
          </View>
        </Animated.View>
      ) : (
        <View style={styles.opts}>
          <Option
            icon={<FileIcon color="#fff" />}
            gradient={['#5B98FF', '#1F4FD8']}
            title="Выбрать файл"
            sub={`PDF до ${MAX_MB} МБ`}
            onPress={pickFile}
          />
          <Option
            icon={<CameraIcon color="#fff" />}
            gradient={['#8AD6FF', '#2B7BEA']}
            title="Сфотографировать"
            sub="До 10 снимков по порядку страниц"
            onPress={shoot}
          />
          <Option
            icon={<GalleryIcon color="#fff" />}
            gradient={['#3A4A70', colors.ink]}
            title="Выбрать из галереи"
            sub="Фото или снимки экрана с нотами"
            onPress={pickGallery}
          />
        </View>
      )}

      <Press
        accessibilityRole="button"
        accessibilityState={{ expanded: adv }}
        onPress={() => setAdv(!adv)}
        scale={1}
        style={styles.advBtn}
      >
        <Text style={styles.advText}>Дополнительные настройки</Text>
        <View style={{ transform: [{ rotate: adv ? '180deg' : '0deg' }] }}>
          <ChevronDownIcon size={18} color={colors.ink2} />
        </View>
      </Press>
      {adv ? (
        <Animated.View
          entering={FadeIn.duration(250)}
          layout={LinearTransition}
          style={styles.advIn}
        >
          <Text style={styles.flabel}>Размер произведения</Text>
          <View style={styles.chips}>
            {METERS.map((m) => (
              <Chip
                key={m}
                label={m === 'auto' ? 'Авто' : m}
                on={meter === m}
                onPress={() => setMeter(m)}
              />
            ))}
          </View>
          <Text style={styles.hint}>
            Не обязательно. Укажите, если в нотах нет знака размера или он распознаётся неверно.
          </Text>
        </Animated.View>
      ) : null}
    </Sheet>
  );
}

function Option({
  icon,
  gradient,
  title,
  sub,
  onPress,
}: {
  icon: React.ReactNode;
  gradient: [string, string];
  title: string;
  sub: string;
  onPress: () => void;
}) {
  return (
    <Press accessibilityRole="button" onPress={onPress} scale={0.98} style={styles.opt}>
      <View style={styles.ico}>
        <LinearGradient
          colors={gradient}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={StyleSheet.absoluteFill}
        />
        {icon}
      </View>
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={styles.otitle}>{title}</Text>
        <Text style={styles.osub}>{sub}</Text>
      </View>
      <ChevronRightIcon size={18} color={colors.ink3} />
    </Press>
  );
}

const styles = StyleSheet.create({
  head: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  h2: { fontFamily: fonts.extrabold, fontSize: 22, letterSpacing: -0.4, color: colors.ink },
  sub: { marginTop: 6, fontFamily: fonts.medium, fontSize: 13, lineHeight: 19, color: colors.ink2 },
  opts: { gap: 8, marginTop: 18 },
  opt: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    paddingVertical: 10,
    paddingLeft: 10,
    paddingRight: 14,
    borderRadius: 24,
    backgroundColor: 'rgba(255,255,255,0.75)',
    borderWidth: 1,
    borderColor: 'rgba(15,25,50,0.06)',
  },
  ico: {
    width: 50,
    height: 50,
    borderRadius: 17,
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
  },
  otitle: { fontFamily: fonts.bold, fontSize: 16, color: colors.ink },
  osub: { fontFamily: fonts.medium, fontSize: 12, color: colors.ink2 },
  shots: {
    marginTop: 18,
    padding: 16,
    gap: 12,
    borderRadius: 22,
    backgroundColor: 'rgba(47,107,255,0.07)',
    borderWidth: 1,
    borderColor: 'rgba(47,107,255,0.2)',
  },
  shotsText: { fontFamily: fonts.semibold, fontSize: 14, color: colors.ink },
  shotsRow: { flexDirection: 'row', gap: 8 },
  advBtn: {
    height: 48,
    marginTop: 12,
    paddingHorizontal: 6,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  advText: { fontFamily: fonts.bold, fontSize: 14, color: colors.ink2 },
  advIn: { paddingHorizontal: 6, paddingTop: 4, paddingBottom: 6 },
  flabel: {
    fontFamily: fonts.bold,
    fontSize: 12,
    letterSpacing: 0.96,
    textTransform: 'uppercase',
    color: colors.ink3,
  },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 },
  hint: {
    marginTop: 10,
    fontFamily: fonts.medium,
    fontSize: 12,
    lineHeight: 17,
    color: colors.ink2,
  },
});
