import { useLocalSearchParams } from 'expo-router';

import { PlaceholderScreen } from '@/components/placeholder-screen';

export default function PieceScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  return (
    <PlaceholderScreen title={`Произведение ${id}`} phase="Фазы 2 и 5">
      Ноты целиком или по N тактов, выбор рук, карта сложности, список фрагментов.
    </PlaceholderScreen>
  );
}
