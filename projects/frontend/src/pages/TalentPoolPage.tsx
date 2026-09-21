import {
  BankOutlined, BookOutlined, DeleteOutlined, EditOutlined, FileTextOutlined,
  FolderOpenOutlined, FolderOutlined, PlusOutlined, TagOutlined,
} from '@ant-design/icons';
import {
  Avatar, Button, Checkbox, Drawer, Empty, Form, Input, Modal, Pagination,
  Popconfirm, Select, Space, Tag, Tree,
} from 'antd';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { PageLoading } from '@/components/PageLoading';
import { fetchJobs } from '@/services/job';
import {
  POOL_SOURCE_TEXT, activatePoolEntry, batchPoolTags,
  batchRemoveFromPool, createPoolFolder, deletePoolFolder, fetchPool, fetchPoolFolders,
  removeFromPool, renamePoolFolder, updatePoolEntry,
} from '@/services/talentPool';
import type { PoolEntry, PoolFolder, PoolFolderSummary } from '@/services/talentPool';
import { msg } from '@/utils/message';
import { useCurrentUser } from '@/services/user';
import { downloadProtectedFile } from '@/services/http';

const CATEGORY_OPTIONS = [
  { value: 'tech', label: '技术类' }, { value: 'product', label: '产品类' },
  { value: 'sales', label: '销售类' }, { value: 'general', label: '综合类' },
];

const STAGE_TEXT: Record<string, string> = {
  new_resume: '接收简历', pending_screen: '简历初筛', hr_screen_passed: '业务复筛',
  business_screen: '业务复筛', interview_1: '一面', interview_2: '二面',
  interview_3: '终面', hr_interview: 'HRBP 面试', offer_approval: '录用审批',
  offer_pending: '待发 Offer', offer: 'Offer', pending_onboard: '待入职',
  onboarded: '已入职', eliminated: '已淘汰', abandoned: '已放弃',
};

function stageText(stage: string | undefined) {
  return STAGE_TEXT[stage ?? ''] ?? '其他阶段';
}

export function TalentPoolPage() {
  const navigate = useNavigate();
  const { user } = useCurrentUser();
  const canManage = user?.role === 'hr';
  const canManageFolders = Boolean(user && (
    user.role === 'super_admin' || user.roles?.includes('super_admin')
  ));
  const [list, setList] = useState<PoolEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({
    keyword: '', category: '', tag: '', source: '', status: '', folder_key: 'all', page: 1,
  });
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [jobs, setJobs] = useState<{ id: number; name: string }[]>([]);

  const [editTarget, setEditTarget] = useState<PoolEntry | null>(null);
  const [editForm] = Form.useForm();
  const [activateTarget, setActivateTarget] = useState<PoolEntry | null>(null);
  const [activateJobId, setActivateJobId] = useState<number | null>(null);
  const [batchTagOpen, setBatchTagOpen] = useState(false);
  const [batchTagForm] = Form.useForm();
  const [folderSummary, setFolderSummary] = useState<PoolFolderSummary | null>(null);
  const [folderKeyword, setFolderKeyword] = useState('');
  const [folderEditor, setFolderEditor] = useState<{ id?: number; name: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchPool({
        keyword: filters.keyword || undefined,
        category: filters.category || undefined,
        tag: filters.tag || undefined,
        source: filters.source || undefined,
        status: filters.status || undefined,
        folder_key: filters.folder_key,
        page: filters.page, page_size: 10,
      });
      setList(data.list);
      setTotal(data.total);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  const loadFolders = useCallback(async () => {
    setFolderSummary(await fetchPoolFolders());
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void loadFolders();
  }, [loadFolders]);

  useEffect(() => {
    fetchJobs({ page_size: 100 }).then((d) => setJobs(d.list.map((j) => ({ id: j.id, name: j.name }))));
  }, []);

  const selectedCustomFolder = useMemo(() => {
    if (!filters.folder_key.startsWith('custom:')) return null;
    return folderSummary?.custom_folders.find((item) => item.key === filters.folder_key) ?? null;
  }, [filters.folder_key, folderSummary]);

  const visibleFolderTree = useMemo(() => {
    const keyword = folderKeyword.trim().toLowerCase();
    if (!keyword) return folderSummary?.tree ?? [];
    const filterNodes = (nodes: PoolFolder[]): PoolFolder[] => nodes.flatMap((node) => {
      const children = filterNodes(node.children ?? []);
      if (node.name.toLowerCase().includes(keyword) || children.length) {
        return [{ ...node, children }];
      }
      return [];
    });
    return filterNodes(folderSummary?.tree ?? []);
  }, [folderKeyword, folderSummary]);

  const treeData = useMemo(() => {
    const convert = (nodes: PoolFolder[]): Parameters<typeof Tree>[0]['treeData'] => nodes.map((node) => ({
      key: node.key,
      selectable: node.selectable !== false,
      icon: node.type === 'root' ? <FolderOpenOutlined /> : <FolderOutlined />,
      title: (
        <span className="talent-folder-title">
          <span>{node.name}</span><em>{node.count}</em>
        </span>
      ),
      children: node.children?.length ? convert(node.children) : undefined,
    }));
    return convert(visibleFolderTree);
  }, [visibleFolderTree]);

  const openEditor = (record: PoolEntry) => {
    setEditTarget(record);
    editForm.setFieldsValue({
      category: record.category, tags: record.tags, reason: record.reason,
      recommended_job_id: record.recommended_job_id,
      folder_id: record.folder_id,
      last_contact_at: record.last_contact_at ? record.last_contact_at.slice(0, 10) : '',
    });
  };

  return (
    <div>
      <div className="page-head">
        <h2 className="page-title">人才库</h2>
        <Space>
          {canManage && <Button
            disabled={!selectedIds.length}
            icon={<TagOutlined />}
            onClick={() => setBatchTagOpen(true)}
          >
            批量改标签
          </Button>}
          {canManage && <Popconfirm
            title={`确认批量移出 ${selectedIds.length} 条记录？`}
            disabled={!selectedIds.length}
            onConfirm={async () => {
              const res = await batchRemoveFromPool(selectedIds);
              msg.success(`已移出 ${res.removed} 条`);
              setSelectedIds([]);
              void load();
              void loadFolders();
            }}
          >
            <Button danger disabled={!selectedIds.length}>批量移出</Button>
          </Popconfirm>}
          {canManage && <Button onClick={() => void downloadProtectedFile(
            `/api/talent-pool/export?folder_key=${encodeURIComponent(filters.folder_key)}`,
            'talent_pool.csv',
          )}>导出</Button>}
        </Space>
      </div>
      <div className="talent-pool-layout">
        <aside className="talent-folder-panel">
          <div className="talent-folder-panel-head">
            <strong>归档目录</strong>
            {canManageFolders && (
              <Button
                type="text" size="small" icon={<PlusOutlined />}
                onClick={() => setFolderEditor({ name: '' })}
                aria-label="新增人才库文件夹"
              />
            )}
          </div>
          <Input.Search
            allowClear size="small" placeholder="搜索文件夹"
            value={folderKeyword} onChange={(event) => setFolderKeyword(event.target.value)}
          />
          <Tree
            showIcon blockNode
            className="talent-folder-tree"
            treeData={treeData}
            selectedKeys={[filters.folder_key]}
            defaultExpandedKeys={['all', 'group:jobs', 'group:custom']}
            onSelect={(keys) => {
              const key = String(keys[0] ?? 'all');
              setSelectedIds([]);
              setFilters((current) => ({ ...current, folder_key: key, page: 1 }));
            }}
          />
          {canManageFolders && selectedCustomFolder && (
            <div className="talent-folder-actions">
              <Button
                size="small" icon={<EditOutlined />}
                onClick={() => setFolderEditor({ id: selectedCustomFolder.id, name: selectedCustomFolder.name })}
              >
                重命名
              </Button>
              <Popconfirm
                title="删除这个文件夹？"
                description="文件夹内候选人将移至“待 HR 归档”。"
                onConfirm={async () => {
                  const result = await deletePoolFolder(Number(selectedCustomFolder.id));
                  msg.success(`文件夹已删除，${result.moved_to_pending_archive} 人移至待归档`);
                  setFilters((current) => ({ ...current, folder_key: 'system:pending_archive', page: 1 }));
                  await loadFolders();
                }}
              >
                <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
              </Popconfirm>
            </div>
          )}
        </aside>
        <div className="hrats-block talent-pool-content">
        <Space style={{ marginBottom: 12 }} wrap>
          <Input.Search
            placeholder="姓名/手机/邮箱" allowClear style={{ width: 200 }}
            onSearch={(v) => setFilters((f) => ({ ...f, keyword: v, page: 1 }))}
          />
          <Select
            placeholder="分类" allowClear style={{ width: 120 }}
            value={filters.category || undefined}
            onChange={(v) => setFilters((f) => ({ ...f, category: v ?? '', page: 1 }))}
            options={CATEGORY_OPTIONS}
          />
          <Input
            placeholder="标签" allowClear style={{ width: 130 }}
            onPressEnter={(e) => setFilters((f) => ({ ...f, tag: (e.target as HTMLInputElement).value, page: 1 }))}
            onBlur={(e) => setFilters((f) => ({ ...f, tag: e.target.value, page: 1 }))}
          />
          <Select
            placeholder="来源" allowClear style={{ width: 140 }}
            value={filters.source || undefined}
            onChange={(v) => setFilters((f) => ({ ...f, source: v ?? '', page: 1 }))}
            options={Object.entries(POOL_SOURCE_TEXT).map(([value, label]) => ({ value, label }))}
          />
          <Select
            placeholder="状态" allowClear style={{ width: 120 }}
            value={filters.status || undefined}
            onChange={(v) => setFilters((f) => ({ ...f, status: v ?? '', page: 1 }))}
            options={[{ value: 'active', label: '待激活' }, { value: 'activated', label: '已激活' }]}
          />
          <Tag color="blue">
            {filters.folder_key === 'all'
              ? '全部归档'
              : [...(folderSummary?.tree[0]?.children ?? []), ...(folderSummary?.tree[0]?.children?.flatMap((item) => item.children ?? []) ?? [])]
                .find((item) => item.key === filters.folder_key)?.name || '当前文件夹'}
          </Tag>
        </Space>
        {loading ? <PageLoading /> : (
          <>
            <div className="candidate-card-select-all">
              <Checkbox
                indeterminate={selectedIds.length > 0 && list.some((item) => !selectedIds.includes(item.id))}
                checked={list.length > 0 && list.every((item) => selectedIds.includes(item.id))}
                onChange={(event) => {
                  const pageIds = list.map((item) => item.id);
                  setSelectedIds((current) => event.target.checked
                    ? Array.from(new Set([...current, ...pageIds]))
                    : current.filter((id) => !pageIds.includes(id)));
                }}
              >
                全选本页
              </Checkbox>
              <span>共 {total} 位人才</span>
            </div>
            <div className="candidate-profile-list">
              {list.length === 0 ? <Empty description="当前文件夹暂无人才" /> : list.map((record) => {
                const candidateTags = (record.candidate_tags || '')
                  .split(/[,，]/).map((item) => item.trim()).filter(Boolean);
                const tags = Array.from(new Set([...candidateTags, ...(record.tags || [])])).slice(0, 3);
                const work = record.work_summary || {};
                const education = record.education_summary || {};
                return (
                  <article
                    className="candidate-profile-card talent-pool-candidate-card"
                    key={record.id}
                    onClick={() => navigate(`/candidates/${record.candidate_id}`)}
                  >
                    <div className="candidate-card-checkbox" onClick={(event) => event.stopPropagation()}>
                      <Checkbox
                        checked={selectedIds.includes(record.id)}
                        onChange={(event) => setSelectedIds((current) => event.target.checked
                          ? Array.from(new Set([...current, record.id]))
                          : current.filter((id) => id !== record.id))}
                      />
                    </div>
                    <Avatar className="candidate-card-avatar" size={58}>
                      {record.candidate_name?.slice(0, 1) || '候'}
                    </Avatar>
                    <div className="candidate-card-main">
                      <div className="candidate-card-name-row">
                        <strong>{record.candidate_name}</strong>
                        {record.folder_key === 'system:eliminated' && <Tag color="error">已淘汰</Tag>}
                        {tags.map((tag) => <Tag key={tag}>{tag}</Tag>)}
                      </div>
                      <div className="candidate-card-brief">
                        <span>{record.gender || '未知'}</span><i />
                        <span>{record.age ? `${record.age}岁` : '年龄未知'}</span><i />
                        <span>{record.city || '城市未填写'}</span>
                      </div>
                      <div className="candidate-card-history">
                        <div className="candidate-history-work">
                          <BankOutlined />
                          <span className="candidate-history-date">
                            {work.start || '时间未填写'} 至 {work.end || '至今'}
                          </span>
                          <strong>{work.company || '暂无工作经历'}</strong>
                        </div>
                        <div className="candidate-history-education">
                          <BookOutlined />
                          <span className="candidate-history-date">{education.graduate_at || '时间未填写'}</span>
                          <strong>{education.degree || record.highest_education || '学历未填写'}</strong>
                          <span>{education.school || '学校未填写'}</span>
                        </div>
                      </div>
                    </div>
                    <div className="candidate-card-side">
                      <Tag color={record.folder_key === 'system:eliminated' ? 'red' : 'blue'}>
                        {record.folder_name}
                      </Tag>
                      <span>{record.latest_application?.job_name || record.recommended_job_name || '未关联职位'}</span>
                      <span>最后阶段：{stageText(record.current_stage)}</span>
                      <span>入库来源：{record.source_text || '-'}</span>
                      {record.reason && <span title={record.reason}>原因：{record.reason}</span>}
                      <span><FileTextOutlined /> 简历附件 {record.resume_count || 0} 份</span>
                    </div>
                    <div className="talent-pool-card-actions" onClick={(event) => event.stopPropagation()}>
                      <Button
                        size="small" type="primary" ghost icon={<FileTextOutlined />}
                        onClick={() => navigate(`/candidates/${record.candidate_id}`)}
                      >
                        查看简历
                      </Button>
                      {canManage && (
                        <>
                          <Button size="small" onClick={() => openEditor(record)}>维护</Button>
                          {record.status === 'active' && (
                            <Button
                              size="small"
                              onClick={() => { setActivateTarget(record); setActivateJobId(null); }}
                            >
                              重新激活
                            </Button>
                          )}
                          <Popconfirm
                            title="确认移出人才库？"
                            onConfirm={async () => {
                              await removeFromPool(record.id);
                              msg.success('已移出人才库');
                              setSelectedIds((current) => current.filter((id) => id !== record.id));
                              void load();
                              void loadFolders();
                            }}
                          >
                            <Button size="small" danger>移出</Button>
                          </Popconfirm>
                        </>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
            {total > 10 && (
              <Pagination
                className="candidate-card-pagination"
                current={filters.page}
                pageSize={10}
                total={total}
                showSizeChanger={false}
                onChange={(page) => setFilters((current) => ({ ...current, page }))}
              />
            )}
          </>
        )}
        </div>
      </div>

      {/* 维护抽屉 */}
      <Drawer
        title={`维护：${editTarget?.candidate_name ?? ''}`} width={480} forceRender
        open={!!editTarget} onClose={() => setEditTarget(null)}
        extra={
          <Button
            type="primary"
            onClick={async () => {
              const values = await editForm.validateFields();
              if (!editTarget) return;
              await updatePoolEntry(editTarget.id, {
                category: values.category ?? '',
                tags: values.tags ?? [],
                reason: values.reason ?? '',
                recommended_job_id: values.recommended_job_id ?? null,
                folder_id: values.folder_id ?? null,
                last_contact_at: values.last_contact_at ?? '',
              });
              msg.success('已更新');
              setEditTarget(null);
              void load();
              void loadFolders();
            }}
          >
            保存
          </Button>
        }
      >
        <Form form={editForm} layout="vertical">
          <Form.Item name="category" label="分类">
            <Select allowClear options={CATEGORY_OPTIONS} />
          </Form.Item>
          <Form.Item name="tags" label="标签">
            <Select mode="tags" placeholder="输入后回车" tokenSeparators={[',']} />
          </Form.Item>
          <Form.Item name="recommended_job_id" label="可推荐职位">
            <Select
              allowClear showSearch optionFilterProp="label"
              options={jobs.map((j) => ({ value: j.id, label: j.name }))}
            />
          </Form.Item>
          <Form.Item name="folder_id" label="自定义归档文件夹">
            <Select
              allowClear
              disabled={editTarget?.folder_key === 'system:eliminated'}
              placeholder={editTarget?.folder_key === 'system:eliminated' ? '淘汰记录固定归入已淘汰' : '不选择则按职位自动归档'}
              options={(folderSummary?.custom_folders ?? []).map((folder) => ({
                value: folder.id, label: folder.name,
              }))}
            />
          </Form.Item>
          <Form.Item name="last_contact_at" label="最近联系时间（YYYY-MM-DD）">
            <Input placeholder="2026-08-01" />
          </Form.Item>
          <Form.Item name="reason" label="加入原因">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Drawer>

      {/* 重新激活弹窗 */}
      <Modal
        title={`重新激活：${activateTarget?.candidate_name ?? ''}`}
        open={!!activateTarget}
        onCancel={() => setActivateTarget(null)}
        onOk={async () => {
          if (!activateTarget || !activateJobId) {
            msg.error('请选择目标职位');
            return;
          }
          await activatePoolEntry(activateTarget.id, activateJobId);
          msg.success('已重新激活，候选人进入新职位流程');
          setActivateTarget(null);
          void load();
          void loadFolders();
        }}
      >
        <p style={{ color: 'rgba(23,26,29,0.6)' }}>
          将为候选人新建目标职位的应聘记录（锁定期与重复投递校验仍然生效）。
        </p>
        <Select
          style={{ width: '100%' }} placeholder="选择招聘中的职位"
          showSearch optionFilterProp="label"
          value={activateJobId ?? undefined}
          onChange={(v) => setActivateJobId(v)}
          options={jobs.map((j) => ({ value: j.id, label: j.name }))}
        />
      </Modal>

      {/* 批量改标签弹窗 */}
      <Modal
        title={`批量修改标签（${selectedIds.length} 条）`}
        open={batchTagOpen}
        onCancel={() => setBatchTagOpen(false)}
        onOk={async () => {
          const values = await batchTagForm.validateFields();
          const res = await batchPoolTags(selectedIds, values.tags ?? [], values.mode);
          msg.success(`已更新 ${res.updated} 条`);
          setBatchTagOpen(false);
          setSelectedIds([]);
          void load();
          void loadFolders();
        }}
      >
        <Form form={batchTagForm} layout="vertical" initialValues={{ mode: 'append' }}>
          <Form.Item name="mode" label="修改方式">
            <Select options={[
              { value: 'append', label: '追加（保留原标签）' },
              { value: 'replace', label: '覆盖（替换原标签）' },
            ]} />
          </Form.Item>
          <Form.Item name="tags" label="标签" rules={[{ required: true, message: '必填' }]}>
            <Select mode="tags" placeholder="输入后回车" tokenSeparators={[',']} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={folderEditor?.id ? '重命名人才库文件夹' : '新增人才库文件夹'}
        open={!!folderEditor}
        onCancel={() => setFolderEditor(null)}
        okText="保存"
        onOk={async () => {
          const name = folderEditor?.name.trim() ?? '';
          if (!name) {
            msg.error('请输入文件夹名称');
            return;
          }
          if (folderEditor?.id) await renamePoolFolder(folderEditor.id, name);
          else await createPoolFolder(name);
          msg.success(folderEditor?.id ? '文件夹已重命名' : '文件夹已新增');
          setFolderEditor(null);
          await loadFolders();
        }}
      >
        <Input
          maxLength={30} placeholder="文件夹名称"
          value={folderEditor?.name ?? ''}
          onChange={(event) => setFolderEditor((current) => current
            ? { ...current, name: event.target.value } : current)}
          onPressEnter={() => undefined}
        />
      </Modal>
    </div>
  );
}
