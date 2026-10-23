import { Alert, Descriptions, Modal, Radio, Space, Tag } from 'antd';

import { saveCandidate } from '@/services/candidate';
import type { DuplicateResult } from '@/services/candidate';
import { msg } from '@/utils/message';

const FIELD_NAMES: Record<string, string> = { name: '姓名', phone: '手机', email: '邮箱' };

function confirmDuplicates(result: DuplicateResult, incoming: Record<string, unknown>) {
  return new Promise<Record<string, string> | null>((resolve) => {
    const exact = result.duplicate_kind === 'exact';
    const candidates = result.duplicates ?? [];
    const decisions: Record<string, string> = {};
    if (exact && candidates[0]) {
      candidates.forEach((candidate, index) => { decisions[String(candidate.id)] = index === 0 ? 'same' : 'different'; });
    }
    Modal.confirm({
      title: exact ? '重复候选人：合并到已有主档' : '疑似重复候选人：请确认身份',
      width: 720,
      maskClosable: false,
      okText: exact ? '确认合并' : '确认并继续',
      cancelText: '取消，返回修改',
      content: (
        <Space direction="vertical" style={{ width: '100%', maxHeight: '60vh', overflowY: 'auto' }} size={16}>
          <Alert type="warning" showIcon message={exact
            ? '姓名、手机、邮箱全部重合，不会新建主档。确认后补充资料到已有档案。'
            : '请逐一确认与历史候选人是否为同一人；全部确认前不会保存候选人或继续招聘流程。'} />
          <Descriptions title="本次录入" column={1} size="small">
            {Object.entries(FIELD_NAMES).map(([field, label]) => (
              <Descriptions.Item key={field} label={label}>
                {typeof incoming[field] === 'string' ? incoming[field] || '未填写' : '未填写'}
              </Descriptions.Item>
            ))}
          </Descriptions>
          {candidates.map((candidate) => (
            <div key={candidate.id}>
              <Descriptions title={`历史候选人 #${candidate.id}`} column={1} size="small">
                <Descriptions.Item label="姓名">{candidate.name}</Descriptions.Item>
                <Descriptions.Item label="手机">{candidate.phone || '未填写'}</Descriptions.Item>
                <Descriptions.Item label="邮箱">{candidate.email || '未填写'}</Descriptions.Item>
                <Descriptions.Item label="招聘 HR">{candidate.owner_name || '未分配'}</Descriptions.Item>
                <Descriptions.Item label="教育经历">
                  {candidate.education?.map((item) => [item.school, item.degree, item.graduate_at].filter(Boolean).join(' ')).join('；') || '未填写'}
                </Descriptions.Item>
                <Descriptions.Item label="工作经历">
                  {candidate.work_experience?.map((item) => [item.company, item.start, item.end].filter(Boolean).join(' ')).join('；') || '未填写'}
                </Descriptions.Item>
                <Descriptions.Item label="重合项">
                  {candidate.matched_fields?.map((field) => <Tag key={field}>{FIELD_NAMES[field] ?? field}</Tag>)}
                </Descriptions.Item>
              </Descriptions>
              {!exact && (
                <Radio.Group onChange={(event) => {
                  const value: unknown = event.target.value;
                  if (value === 'same' || value === 'different') decisions[String(candidate.id)] = value;
                }}>
                  <Radio value="same">同一人，合并到此主档</Radio>
                  <Radio value="different">非同一人</Radio>
                </Radio.Group>
              )}
            </div>
          ))}
        </Space>
      ),
      onOk: () => {
        if (candidates.some((candidate) => !decisions[String(candidate.id)])) {
          msg.warning('请逐一确认所有疑似重复候选人');
          return Promise.reject(new Error('Identity confirmation required'));
        }
        if (Object.values(decisions).filter((value) => value === 'same').length > 1) {
          msg.warning('只能选择一个主档作为同一人，其余请选择非同一人');
          return Promise.reject(new Error('Select one master profile'));
        }
        resolve(decisions);
      },
      onCancel: () => resolve(null),
    });
  });
}

/** Only return a saved result once every server-side identity challenge is resolved. */
export async function saveCandidateWithReview(
  id: number | null, payload: Record<string, unknown>, initialResult?: DuplicateResult,
) {
  let result = initialResult ?? await saveCandidate(id, payload);
  while (result.duplicated) {
    if (!result.duplicates?.length || !result.review_token) {
      msg.warning('查重结果发生变化，请刷新后重新提交');
      return null;
    }
    const decisions = await confirmDuplicates(result, payload);
    if (!decisions) return null;
    result = await saveCandidate(id, {
      ...payload,
      duplicate_review: { token: result.review_token, decisions },
    });
  }
  return result;
}
