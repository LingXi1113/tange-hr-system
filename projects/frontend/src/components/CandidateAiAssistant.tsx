import { RobotOutlined, SendOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { Avatar, Button, Drawer, FloatButton, Input, Space, Tag, Typography } from 'antd';
import { useMemo, useState } from 'react';

import type { CandidateDetail } from '@/services/candidate';
import type { ScreeningResult } from '@/services/screening';
import { buildCandidateAssistantReply } from '@/utils/localAi';

interface Message {
  role: 'assistant' | 'user';
  content: string;
}

const SUGGESTIONS = [
  '概括候选人简历',
  '解释与当前岗位的匹配度',
  '生成本轮面试问题',
  '列出需要人工核实的风险',
];

export function CandidateAiAssistant({
  candidate,
  screening,
}: {
  candidate: CandidateDetail;
  screening: ScreeningResult | null;
}) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const welcome = useMemo(() => (
    `你好，我是招聘 AI 助手。我可以结合 ${candidate.name} 的简历${screening ? '和当前岗位匹配结果' : ''}，帮你快速总结、生成追问并提示待核实信息。`
  ), [candidate.name, screening]);
  const [messages, setMessages] = useState<Message[]>([]);

  function ask(value: string) {
    const question = value.trim();
    if (!question) return;
    setMessages((current) => [
      ...current,
      { role: 'user', content: question },
      { role: 'assistant', content: buildCandidateAssistantReply(question, candidate, screening) },
    ]);
    setInput('');
  }

  return (
    <>
      <FloatButton
        icon={<RobotOutlined />}
        tooltip="招聘 AI 助手"
        type="primary"
        style={{ right: 28, bottom: 28, width: 52, height: 52 }}
        onClick={() => setOpen(true)}
      />
      <Drawer
        title={(
          <Space>
            <Avatar style={{ background: 'linear-gradient(135deg, #1677ff, #7c3aed)' }} icon={<RobotOutlined />} />
            <span>招聘 AI 助手</span>
            <Tag color="purple">本地演示</Tag>
          </Space>
        )}
        width={440}
        open={open}
        onClose={() => setOpen(false)}
        styles={{ body: { padding: 0, display: 'flex', flexDirection: 'column' } }}
      >
        <div style={{ padding: '14px 16px', background: '#f6f8fc', borderBottom: '1px solid #eef0f4' }}>
          <Typography.Text type="secondary">
            <ThunderboltOutlined style={{ color: '#7c3aed', marginRight: 6 }} />
            当前回答来自本地规则和已有招聘数据，未来配置 API Key 后可切换为大模型分析。
          </Typography.Text>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: 16, minHeight: 360 }}>
          <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
            <Avatar size="small" style={{ background: '#1677ff' }} icon={<RobotOutlined />} />
            <div style={{ maxWidth: 330, padding: '10px 12px', borderRadius: '4px 14px 14px', background: '#f0f5ff', lineHeight: 1.7 }}>
              {welcome}
            </div>
          </div>
          {!messages.length && (
            <Space direction="vertical" style={{ width: '100%' }}>
              <Typography.Text type="secondary">你可能想问</Typography.Text>
              {SUGGESTIONS.map((item) => (
                <Button key={item} block style={{ textAlign: 'left', height: 40 }} onClick={() => ask(item)}>
                  {item}
                </Button>
              ))}
            </Space>
          )}
          {messages.map((message, index) => (
            <div
              key={`${message.role}-${index}`}
              style={{ display: 'flex', justifyContent: message.role === 'user' ? 'flex-end' : 'flex-start', marginBottom: 14 }}
            >
              <div style={{
                maxWidth: 340,
                whiteSpace: 'pre-wrap',
                padding: '10px 12px',
                borderRadius: message.role === 'user' ? '14px 4px 14px 14px' : '4px 14px 14px',
                color: message.role === 'user' ? '#fff' : '#1f2937',
                background: message.role === 'user' ? '#1677ff' : '#f0f5ff',
                lineHeight: 1.7,
              }}>
                {message.content}
              </div>
            </div>
          ))}
        </div>
        <div style={{ padding: 16, borderTop: '1px solid #eef0f4', background: '#fff' }}>
          <Space.Compact style={{ width: '100%' }}>
            <Input.TextArea
              autoSize={{ minRows: 1, maxRows: 4 }}
              value={input}
              placeholder="向 AI 助手提问…"
              onChange={(event) => setInput(event.target.value)}
              onPressEnter={(event) => {
                if (!event.shiftKey) {
                  event.preventDefault();
                  ask(input);
                }
              }}
            />
            <Button type="primary" icon={<SendOutlined />} style={{ height: 'auto' }} onClick={() => ask(input)} />
          </Space.Compact>
          <Typography.Text type="secondary" style={{ display: 'block', fontSize: 12, marginTop: 8, textAlign: 'center' }}>
            AI 结论仅供辅助，录用决策由 HR 和业务负责人完成
          </Typography.Text>
        </div>
      </Drawer>
    </>
  );
}
