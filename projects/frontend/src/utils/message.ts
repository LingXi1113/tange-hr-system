import type { MessageInstance } from 'antd/es/message/interface';

/**
 * 统一消息封装：通过 Ant Design <App> 上下文注入 message 实例，
 * 避免静态 message 脱离 context 导致的主题警告。
 * 在 MessageBinder 挂载前调用时静默降级为 no-op。
 */
let instance: MessageInstance | null = null;

export function bindMessageInstance(next: MessageInstance) {
  instance = next;
}

type Content = string;

export const msg = {
  success(content: Content) {
    instance?.success(content);
  },
  error(content: Content) {
    instance?.error(content);
  },
  info(content: Content) {
    instance?.info(content);
  },
  warning(content: Content) {
    instance?.warning(content);
  },
};
