/**
 * 角色切换器仅在开发环境（vite dev server，import.meta.env.DEV=true）启用；
 * 生产构建自动隐藏。可通过 VITE_ENABLE_ROLE_SWITCHER=false 在开发环境强制关闭。
 * 与应用类型（normal/embedded）无关：内嵌模式下平台免登失败时仍需 Mock 演示能力。
 */
export const isRoleSwitcherEnabled =
  import.meta.env.DEV && import.meta.env.VITE_ENABLE_ROLE_SWITCHER !== 'false';
