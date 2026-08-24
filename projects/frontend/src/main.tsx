import ReactDOM from 'react-dom/client';
import { HashRouter } from 'react-router-dom';

import { App } from './App';
import { prepareApplication } from './bootstrap/appBootstrap';
import { fetchCurrentUser } from './services/user';
import './styles/index.less';
import { initializeTracking } from './tracking';
import { ParentNavigationBridge } from './components/ParentNavigationBridge';

function renderApp() {
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <HashRouter>
      {/*  don't delete */}
      <ParentNavigationBridge />
      <App />
    </HashRouter>,
  );
}

async function bootstrap() {
  const embeddedUserId = await prepareApplication();
  initializeTracking(embeddedUserId);
  // 渲染前先确认登录态：未登录时由 RequireAuth 守卫引导到登录页
  await fetchCurrentUser();
  renderApp();
}

void bootstrap();
