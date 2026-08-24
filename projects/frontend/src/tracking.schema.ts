import type {
  TrackingProjectSchemaInput,
  TrackingPropertySchema,
} from '@/lib/jahead-track-frontend-sdk';

const trackingDiagnosticProperties = {
  tracking_project_id_missing: {
    type: 'boolean',
    name: 'PROJECT_ID 是否缺失',
    sensitive: false,
  },
  tracking_company_id_missing: {
    type: 'boolean',
    name: 'COMPANY_ID 是否缺失',
    sensitive: false,
  },
  tracking_user_id_missing: {
    type: 'boolean',
    name: '用户 ID 是否缺失',
    sensitive: false,
  },
  tracking_missing_fields: {
    type: 'string',
    name: '缺失的埋点字段',
    sensitive: false,
  },
} satisfies Record<string, TrackingPropertySchema>;

export const trackingSchema: TrackingProjectSchemaInput = {
  project_name: 'Frontend Scaffold',
  schema_version: '1.0.1',
  timezone: 'Asia/Shanghai',
  events: [
    {
      event_key: 'page_view',
      event_type: 'page_view',
      event_name: '页面浏览',
      description: '应用页面加载完成后上报，同一次页面加载只计一次 PV',
      source: 'frontend',
      properties_schema: {
        route_path: {
          type: 'string',
          name: '路由路径',
          required: true,
          sensitive: false,
        },
        route_search: {
          type: 'string',
          name: '路由查询参数',
          sensitive: false,
        },
        ...trackingDiagnosticProperties,
      },
    },
    {
      event_key: 'page_leave',
      event_type: 'page_leave',
      event_name: '页面离开',
      description: '用户离开页面时上报停留时长',
      source: 'frontend',
      properties_schema: {
        duration_ms: {
          type: 'number',
          name: '停留时长',
          unit: 'ms',
          sensitive: false,
        },
        ...trackingDiagnosticProperties,
      },
    },
  ],
};
