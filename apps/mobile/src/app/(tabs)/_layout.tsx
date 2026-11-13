import { Tabs } from 'expo-router/tabs';

import { Dock } from '@/components/dock';
import { AddSheetProvider, useOpenAddSheet } from '@/features/library/add-sheet';
import { colors } from '@/theme/tokens';

/** Приложение открывается на библиотеке. */
export const unstable_settings = { anchor: 'library' };

export default function TabsLayout() {
  return (
    <AddSheetProvider>
      <TabsWithDock />
    </AddSheetProvider>
  );
}

function TabsWithDock() {
  const openAddSheet = useOpenAddSheet();
  return (
    <Tabs
      backBehavior="initialRoute"
      screenOptions={{ headerShown: false, sceneStyle: { backgroundColor: colors.bg } }}
      tabBar={(props) => <Dock {...props} onAdd={openAddSheet} />}
    >
      <Tabs.Screen name="index" />
      <Tabs.Screen name="library" />
      <Tabs.Screen name="profile" />
    </Tabs>
  );
}
