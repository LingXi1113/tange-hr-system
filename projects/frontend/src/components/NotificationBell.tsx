import { BellOutlined } from '@ant-design/icons';
import { Badge, Button, Empty, List, Popover, Tag } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import {
  NOTIFICATION_SCENE_TEXT, fetchNotifications, fetchUnreadCount,
  markAllNotificationsRead, markNotificationRead,
} from '@/services/notification';
import type { NotificationItem } from '@/services/notification';

const POLL_INTERVAL_MS = 30_000;

/** 顶部通知入口：未读角标 + 最近通知弹层（点击跳转并标记已读）。 */
export function NotificationBell() {
  const navigate = useNavigate();
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [open, setOpen] = useState(false);

  const refreshCount = useCallback(async () => {
    try {
      const data = await fetchUnreadCount();
      setUnread(data.count);
    } catch {
      /* 静默：不打扰用户 */
    }
  }, []);

  const refreshList = useCallback(async () => {
    try {
      const data = await fetchNotifications({ page: 1, page_size: 8 });
      setItems(data.list);
    } catch {
      /* 静默 */
    }
  }, []);

  useEffect(() => {
    void refreshCount();
    const timer = setInterval(() => void refreshCount(), POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [refreshCount]);

  async function handleClickItem(item: NotificationItem) {
    if (item.unread) {
      await markNotificationRead(item.id).catch(() => undefined);
    }
    setOpen(false);
    void refreshCount();
    if (item.route) {
      navigate(item.route);
    }
  }

  const content = (
    <div style={{ width: 340 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ fontWeight: 500 }}>站内通知</span>
        <Button
          size="small" type="link" style={{ padding: 0 }}
          onClick={async () => {
            await markAllNotificationsRead().catch(() => undefined);
            setUnread(0);
            void refreshList();
          }}
        >
          全部已读
        </Button>
      </div>
      {items.length === 0 ? (
        <Empty description="暂无通知" style={{ margin: '12px 0' }} />
      ) : (
        <List
          size="small"
          dataSource={items}
          renderItem={(item) => (
            <List.Item
              style={{ cursor: 'pointer', paddingInline: 4 }}
              onClick={() => void handleClickItem(item)}
            >
              <List.Item.Meta
                title={
                  <span>
                    {item.unread && (
                      <Badge status="processing" style={{ marginRight: 6 }} />
                    )}
                    <Tag style={{ marginInlineEnd: 4 }}>
                      {NOTIFICATION_SCENE_TEXT[item.scene] ?? item.scene}
                    </Tag>
                    {item.title}
                  </span>
                }
                description={
                  <span style={{ fontSize: 12 }}>
                    {item.content}
                    <br />
                    {item.created_at}
                  </span>
                }
              />
            </List.Item>
          )}
        />
      )}
      <div style={{ textAlign: 'center', marginTop: 8 }}>
        <Button
          size="small" type="link"
          onClick={() => {
            setOpen(false);
            navigate('/notifications');
          }}
        >
          查看全部
        </Button>
      </div>
    </div>
  );

  return (
    <Popover
      content={content}
      trigger="click"
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (v) void refreshList();
      }}
      placement="bottomRight"
    >
      <span style={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'center' }}>
        <Badge count={unread} size="small" offset={[2, -2]}>
          <BellOutlined style={{ fontSize: 16, color: 'rgba(255,255,255,0.85)' }} />
        </Badge>
      </span>
    </Popover>
  );
}
