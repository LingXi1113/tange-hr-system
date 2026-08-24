import { Button, Card, Checkbox, Descriptions, Form, Input, Result, Select, Upload } from 'antd';
import type { UploadFile } from 'antd';
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';

import { PageLoading } from '@/components/PageLoading';
import { applyPublicJob, fetchPublicJob } from '@/services/job';
import type { PublicJob } from '@/services/job';
import { msg } from '@/utils/message';

/**
 * 职位公开页（免登录）：职位信息 + 简易投递表单。
 * 无账号无登录；隐私授权必勾选。
 */
export function PublicJobPage() {
  const { token = '' } = useParams();
  const [job, setJob] = useState<PublicJob | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [form] = Form.useForm();

  useEffect(() => {
    if (!token) return;
    fetchPublicJob(token)
      .then(setJob)
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
  }, [token]);

  async function handleSubmit() {
    const values = await form.validateFields();
    if (!values.privacy) {
      msg.error('请先阅读并勾选隐私授权');
      return;
    }
    const data = new FormData();
    data.append('name', values.name);
    data.append('phone', values.phone);
    data.append('email', values.email ?? '');
    data.append('city', values.city ?? '');
    data.append('expected_salary', values.expected_salary ?? '');
    data.append('onboard_time', values.onboard_time ?? '');
    data.append('privacy_agreed', '1');
    const file = files[0]?.originFileObj;
    if (file) data.append('resume', file);
    setSubmitting(true);
    try {
      await applyPublicJob(token, data);
      setDone(true);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="public-job-page">
      <div className="public-topbar">
        <span className="logo-dot" />
        <span>HR招聘 · 职位公开页</span>
      </div>
      <div className="public-body">
        {loading ? (
          <PageLoading />
        ) : notFound || !job ? (
          <Card><Result status="404" title="职位不存在或链接已失效" /></Card>
        ) : done ? (
          <Card>
            <Result status="success" title="投递成功" subTitle="感谢您的投递，HR 将尽快与您联系。" />
          </Card>
        ) : (
          <>
            <Card title={job.name} style={{ marginBottom: 16 }}>
              <Descriptions column={2} size="small">
                <Descriptions.Item label="部门">{job.dept_name || '-'}</Descriptions.Item>
                <Descriptions.Item label="工作地点">{job.location || '-'}</Descriptions.Item>
                <Descriptions.Item label="职位类型">{job.job_type}</Descriptions.Item>
                <Descriptions.Item label="招聘人数">{job.headcount}</Descriptions.Item>
                <Descriptions.Item label="薪资范围" span={2}>{job.salary_range || '面议'}</Descriptions.Item>
              </Descriptions>
              <h4 style={{ marginTop: 12 }}>职位描述</h4>
              <p style={{ whiteSpace: 'pre-wrap', color: 'rgba(23,26,29,0.6)' }}>{job.description || '-'}</p>
              <h4>任职资格</h4>
              <p style={{ whiteSpace: 'pre-wrap', color: 'rgba(23,26,29,0.6)' }}>{job.qualification || '-'}</p>
            </Card>
            <Card title="投递简历">
              {!job.accepting ? (
                <Result status="info" title="该职位当前已停止接收投递" />
              ) : (
                <Form form={form} layout="vertical">
                  <Form.Item name="name" label="姓名" rules={[{ required: true, message: '必填' }]}>
                    <Input />
                  </Form.Item>
                  <Form.Item
                    name="phone" label="手机号"
                    rules={[{ required: true, message: '必填' }, { pattern: /^1[3-9]\d{9}$/, message: '手机号格式不正确' }]}
                  >
                    <Input />
                  </Form.Item>
                  <Form.Item
                    name="email" label="邮箱"
                    rules={[{ type: 'email', message: '邮箱格式不正确' }]}
                  >
                    <Input />
                  </Form.Item>
                  <Form.Item label="应聘职位">
                    <Select value={job.name} options={[{ value: job.name, label: job.name }]} />
                  </Form.Item>
                  <Form.Item name="city" label="城市">
                    <Input />
                  </Form.Item>
                  <Form.Item name="expected_salary" label="期望薪资">
                    <Input placeholder="例如：25k-30k" />
                  </Form.Item>
                  <Form.Item name="onboard_time" label="到岗时间">
                    <Input placeholder="例如：随时 / 一个月内" />
                  </Form.Item>
                  <Form.Item label="简历附件（PDF/Word/图片）">
                    <Upload
                      maxCount={1}
                      fileList={files}
                      beforeUpload={() => false}
                      onChange={({ fileList }) => setFiles(fileList)}
                    >
                      <Button>选择简历文件</Button>
                    </Upload>
                  </Form.Item>
                  <Form.Item name="privacy" valuePropName="checked" rules={[{
                    validator: (_, v) => (v ? Promise.resolve() : Promise.reject(new Error('请先勾选隐私授权'))),
                  }]}>
                    <Checkbox>
                      我已知晓并同意贵司依据《个人信息保护法》收集和处理我的个人简历信息，仅用于本次招聘用途。
                    </Checkbox>
                  </Form.Item>
                  <Button type="primary" block loading={submitting} onClick={() => void handleSubmit()}>
                    提交投递
                  </Button>
                </Form>
              )}
            </Card>
          </>
        )}
      </div>
    </div>
  );
}
