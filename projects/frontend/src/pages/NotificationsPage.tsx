import { Alert, Button, List, Radio, Tag } from 'antd';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { PageLoading } from '@/components/PageLoading';
import {
  NOTIFICATION_SCENE_TEXT, fetchNotifications, markAllNotificationsRead,
  markNotificationRead,
} from '@/services/notification';
import type { NotificationItem } from '@/services/notification';

export function NotificationsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const status = searchParams.get('status') === 'unread' ? 'unread' : 'all';
  const sceneGroup = searchParams.get('scene_group') === 'deadline' ? 'deadline' : '';
  const setStatus = (value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value === 'unread') next.set('status', value); else next.delete('status');
    setSearchParams(next);
  };
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const requestId = useRef(0);

  const load = useCallback(async () => {
    const currentRequest = ++requestId.current;
    setLoading(true);
    setLoadError(false);
    try {
      const data = await fetchNotifications({ status, scene_group: sceneGroup || undefined, page, page_size: 10 });
      if (currentRequest !== requestId.current) return;
      setItems(data.list);
      setTotal(data.total);
    } catch {
      if (currentRequest === requestId.current) setLoadError(true);
    } finally {
      if (currentRequest === requestId.current) setLoading(false);
    }
  }, [status, sceneGroup, page]);
  useEffect(() => { setPage(1); }, [status, sceneGroup]);

  useEffect(() => {
    void load();
    return () => { requestId.current += 1; };
  }, [load]);

  async function handleClick(item: NotificationItem) {
    if (item.unread) {
      await markNotificationRead(item.id).catch(() => undefined);
    }
    void load();
    if (item.route) {
      navigate(item.route);
    }
  }

  return (
    <div>
      <div className="page-head">
        <h2 className="page-title">站内通知</h2>
        <Button
          disabled={Boolean(sceneGroup)} title={sceneGroup ? "筛选视图请逐条阅读通知，避免将其他类型通知一并标记已读" : undefined}
          onClick={async () => {
            await markAllNotificationsRead().catch(() => undefined);
            void load();
          }}
        >
          全部已读
        </Button>
      </div>
      {sceneGroup === 'deadline' && <div style={{ marginBottom: 12 }}>
        <Tag color="orange">到期与逾期提醒</Tag>
        <Button type="link" onClick={() => { const next = new URLSearchParams(searchParams);
          next.delete('scene_group'); setSearchParams(next); }}>查看全部类型</Button>
      </div>}
      {loadError && <Alert style={{ marginBottom: 12 }} type="warning" showIcon message="通知加载失败，请重试"
        action={<Button onClick={() => void load()}>重试</Button>} />}
      <div className="hrats-block">
        <Radio.Group
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(1);
          }}
          style={{ marginBottom: 12 }}
          options={[
            { value: 'all', label: '全部' },
            { value: 'unread', label: '未读' },
          ]}
          optionType="button"
        />
        {loading ? (
          <PageLoading />
        ) : (
          <List
            dataSource={items}
            locale={{ emptyText: '暂无通知' }}
            pagination={{
              current: page, pageSize: 10, total,
              onChange: (p) => setPage(p),
              hideOnSinglePage: true,
            }}
            renderItem={(item) => (
              <List.Item
                style={{ cursor: 'pointer' }}
                onClick={() => void handleClick(item)}
                actions={[
                  item.unread ? <Tag color="processing" key="u">未读</Tag> : <Tag key="r">已读</Tag>,
                ]}
              >
                <List.Item.Meta
                  title={
                    <span>
                      <Tag style={{ marginInlineEnd: 6 }}>
                        {NOTIFICATION_SCENE_TEXT[item.scene] ?? item.scene}
                      </Tag>
                      {item.title}
                    </span>
                  }
                  description={`${item.content} · ${item.created_at}`}
                />
              </List.Item>
            )}
          />
        )}
      </div>
    </div>
  );
}
