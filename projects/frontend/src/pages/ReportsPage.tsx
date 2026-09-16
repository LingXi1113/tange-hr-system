import {
  BarChartOutlined,
  CalendarOutlined,
  CheckCircleOutlined,
  FilterOutlined,
  FundProjectionScreenOutlined,
  PieChartOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';

interface StatisticsModule {
  title: string;
  description: string;
  icon: ReactNode;
  color: string;
  path?: string;
}

interface StatisticsSection {
  title: string;
  modules: StatisticsModule[];
}

const sections: StatisticsSection[] = [
  {
    title: '招聘结果',
    modules: [
      {
        title: '职位招聘进展',
        description: '各个职位招聘进度分析',
        icon: <FundProjectionScreenOutlined />,
        color: '#5b9df9',
        path: '/reports/job-progress',
      },
      {
        title: 'HR进展',
        description: 'HR日常工作量分析',
        icon: <BarChartOutlined />,
        color: '#63c99a',
        path: '/reports/hr-progress',
      },
      {
        title: '招聘月报',
        description: '以月、周、日维度统计关键指标',
        icon: <CalendarOutlined />,
        color: '#3aa9f7',
      },
    ],
  },
  {
    title: '过程转化',
    modules: [
      {
        title: '阶段转化漏斗',
        description: '招聘全流程漏斗分析，支持切换不同流程',
        icon: <FilterOutlined />,
        color: '#5b9df9',
        path: '/reports/stage-funnel',
      },
      {
        title: '招聘渠道效果',
        description: '各渠道关键数据分析',
        icon: <PieChartOutlined />,
        color: '#63c99a',
        path: '/reports/channel-effect',
      },
      {
        title: '面试官效率',
        description: '面试官简历反馈速度、面试数据分析',
        icon: <CheckCircleOutlined />,
        color: '#ff9a5c',
        path: '/reports/interviewer-efficiency',
      },
    ],
  },
  {
    title: '人才分析',
    modules: [
      {
        title: '人才画像',
        description: '候选人特征分布',
        icon: <TeamOutlined />,
        color: '#5b9df9',
        path: '/reports/talent-profile',
      },
    ],
  },
];

export function ReportsPage() {
  const navigate = useNavigate();

  return (
    <div className="statistics-page">
      <div className="page-head">
        <h2 className="page-title">统计</h2>
      </div>
      <div className="statistics-content">
        {sections.map((section) => (
          <section className="statistics-section" key={section.title}>
            <h3 className="statistics-section-title">{section.title}</h3>
            <div className="statistics-module-grid">
              {section.modules.map((module) => (
                <button
                  className={`statistics-module-card${module.path ? ' is-enabled' : ''}`}
                  key={module.title}
                  type="button"
                  disabled={!module.path}
                  onClick={() => module.path && navigate(module.path)}
                >
                  <span className="statistics-module-icon" style={{ color: module.color }}>
                    {module.icon}
                  </span>
                  <span>
                    <span className="statistics-module-title">{module.title}</span>
                    <span className="statistics-module-description">{module.description}</span>
                  </span>
                </button>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
