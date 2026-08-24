import { Button, List, Radio, Tag } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { PageLoading } from '@/components/PageLoading';
import {
  NOTIFICATION_SCENE_TEXT, fetchNotifications, markAllNotificationsRead,
  markNotificationRead,
} from '@/services/notification';
import type { NotificationItem } from '@/services/notification';

export function NotificationsPage() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<'all' | 'unread'>('all');
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchNotifications({ status, page, page_size: 10 });
      setItems(data.list);
      setTotal(data.total);
    } finally {
      setLoading(false);
    }
  }, [status, page]);

  useEffect(() => {
    void load();
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
          onClick={async () => {
            await markAllNotificationsRead().catch(() => undefined);
            void load();
          }}
        >
          全部已读
        </Button>
      </div>
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
