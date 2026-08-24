import { App as AntdApp, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { useEffect } from 'react';

import { TrackingPageViewReporter } from '@/components/TrackingPageViewReporter';
import { RouterView } from '@/routes';
import { theme } from '@/styles/theme';
import { bindMessageInstance } from '@/utils/message';

/** 将 AntD App 上下文中的 message 实例绑定到全局 msg 封装。 */
function MessageBinder() {
  const { message } = AntdApp.useApp();
  useEffect(() => {
    bindMessageInstance(message);
  }, [message]);
  return null;
}

export function App() {
  return (
    <ConfigProvider locale={zhCN} theme={theme}>
      <AntdApp>
        <MessageBinder />
        <RouterView />
        <TrackingPageViewReporter />
      </AntdApp>
    </ConfigProvider>
  );
}
