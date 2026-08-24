import type { ThemeConfig } from 'antd';

/**
 * Jahead-AI 设计 token（对齐 .prd_details/preview/assets/styles.css）：
 * 深色顶栏 #17191B、白色侧边栏、页面底色 #F7F8FC、金橙强调色 #CD9324。
 */
export const theme: ThemeConfig = {
  token: {
    colorPrimary: '#CD9324',
    colorLink: '#A66E16',
    colorLinkHover: '#BE8412',
    colorSuccess: '#00B042',
    colorWarning: '#FFAA00',
    colorError: '#FF5219',
    colorInfo: '#007FFF',
    colorText: '#171A1D',
    colorTextSecondary: 'rgba(23, 26, 29, 0.60)',
    borderRadius: 6,
    fontSize: 14,
    fontFamily: '"PingFang SC", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  },
  components: {
    Layout: {
      bodyBg: '#F7F8FC',
      headerBg: '#17191B',
      headerHeight: 52,
      headerPadding: '0 20px',
      siderBg: '#FFFFFF',
    },
    Menu: {
      itemBg: '#FFFFFF',
      itemSelectedBg: '#F9F2E5',
      itemSelectedColor: '#A66E16',
      itemHoverBg: '#F7F8FC',
      itemBorderRadius: 6,
    },
    Card: {
      borderRadiusLG: 8,
    },
  },
};
