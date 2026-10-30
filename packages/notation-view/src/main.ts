/**
 * Точка входа бандла WebView. Загрузка Verovio и рендер — задача спайка (docs/ROADMAP.md, фаза 1).
 */
import type { HostToViewMessage, ViewToHostMessage } from './protocol';

declare global {
  interface Window {
    ReactNativeWebView?: { postMessage(data: string): void };
  }
}

function post(message: ViewToHostMessage) {
  window.ReactNativeWebView?.postMessage(JSON.stringify(message));
}

function handle(message: HostToViewMessage) {
  switch (message.type) {
    // TODO(фаза 1): load → toolkit.loadData, showRange → select + renderToSVG, highlight → CSS-классы
    default:
      post({ type: 'error', message: `Not implemented: ${message.type}` });
  }
}

// react-native-webview доставляет сообщения на document (Android) и window (iOS)
const onMessage = (e: Event) => handle(JSON.parse((e as MessageEvent<string>).data));
window.addEventListener('message', onMessage);
document.addEventListener('message', onMessage);

post({ type: 'ready', verovioVersion: 'not-loaded' });
