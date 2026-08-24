import { Empty } from 'antd';
import type { ReactNode } from 'react';

interface PlaceholderPageProps {
  title: string;
  description?: string;
  extra?: ReactNode;
}

/**
 * P0 阶段业务模块占位页：统一空状态呈现。
 * 各业务模块实现后（P1+）逐个替换。
 */
export function PlaceholderPage({ title, description, extra }: PlaceholderPageProps) {
  return (
    <div>
      <div className="page-head">
        <h2 className="page-title">{title}</h2>
      </div>
      <div className="hrats-block empty-holder">
        <Empty description={description ?? '模块建设中，将在后续阶段交付'}>{extra}</Empty>
      </div>
    </div>
  );
}
