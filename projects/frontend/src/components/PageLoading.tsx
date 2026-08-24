import { Spin } from 'antd';

/** 统一加载状态。 */
export function PageLoading({ tip = '加载中…' }: { tip?: string }) {
  return (
    <div className="empty-holder">
      <Spin size="large" tip={tip}>
        <div style={{ width: 120 }} />
      </Spin>
    </div>
  );
}
