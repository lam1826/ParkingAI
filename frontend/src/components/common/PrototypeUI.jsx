import { useContext } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { AuthContext } from '../../context/AuthContext';
import { useExpansion } from '../../context/ExpansionContext';
import { workspaceTabs } from '../../utils/navigationItems';

const paths = {
  car: 'M5 17H3V9l2-5h14l2 5v8h-2M5 17v3H3v-3m16 0v3h2v-3M3 10h18M7 14h2m6 0h2M5 17h14',
  bike: 'M5 19a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm14 0a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM5 15l5-8 5 8H5m5-8h5m-5 0H7m8 8 3-11h3',
  parking: 'M6 21V3h7a6 6 0 0 1 0 12H6m0-8h7a2 2 0 0 1 0 4H6',
  calendar: 'M8 2v4m8-4v4M3 10h18M5 4h14a2 2 0 0 1 2 2v14H3V6a2 2 0 0 1 2-2Zm3 10h3m-3 4h6',
  ticket: 'M3 6h18v4a2 2 0 0 0 0 4v4H3v-4a2 2 0 0 0 0-4V6Zm12 0v3m0 6v3m0-7v2',
  help: 'M21 11a9 9 0 1 0-4 7l4 3v-6m-12-7a3 3 0 1 1 4 3l-1 1m0 3v.1',
  camera: 'M3 7h4l2-3h6l2 3h4v13H3V7Zm9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z',
  users: 'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM2 21v-3a7 7 0 0 1 14 0v3m0-17a4 4 0 0 1 0 8m3 3a6 6 0 0 1 3 6',
  shield: 'm12 2 8 3v7c0 5-8 10-8 10S4 17 4 12V5l8-3Zm-4 10 3 3 5-6',
  settings: 'M4 7h16M4 17h16M8 4v6m8 4v6',
  history: 'M3 11a9 9 0 1 1 2 7M3 4v7h7m2-4v6l3 2',
  chart: 'M3 3v18h18M7 16v-5m5 5V6m5 10v-8',
  wallet: 'M20 8H5a2 2 0 0 1 0-4h13v4M3 6v14h18V8m0 4h-6v4h6',
  arrow: 'M4 12h16m-6-6 6 6-6 6', plus: 'M12 4v16M4 12h16',
  check: 'm5 12 4 4L19 6', close: 'm6 6 12 12M6 18 18 6',
  search: 'M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14Zm5-2 6 6',
  clock: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 4v6l4 2',
  user: 'M12 12a5 5 0 1 0 0-10 5 5 0 0 0 0 10Zm-9 9a9 9 0 0 1 18 0',
  logout: 'M9 3H3v18h6m4-14 5 5-5 5m-5-5h13',
  reset: 'M3 4v6h6M3 10a9 9 0 1 1 1 8',
  spark: 'M12 3v3m0 12v3M3 12h3m12 0h3m-9-5 2 4 4 2-4 2-2 4-2-4-4-2 4-2 2-4Z',
};
export function PrototypeIcon({ name, ...props }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}><path d={paths[name] || paths.parking} /></svg>;
}
export function PrototypeBrand() {
  return <div className="brand"><svg className="brand-mark" viewBox="0 0 38 40" aria-hidden="true"><rect x="1" y="2" width="35" height="35" rx="10" fill="#1767bd" /><path d="M13 28V11h8a6 6 0 0 1 0 12h-8m0-8h8a2 2 0 0 1 0 4h-8" stroke="white" strokeWidth="2.5" fill="none" /></svg><span>ParkingAI<small>Một bãi xe. Mọi thứ rõ ràng.</small></span></div>;
}
export function PageHeader({ title, description, actions, children }) {
  return <div className="page-head demo-page-head"><div><h1>{title}</h1>{description && <p>{description}</p>}</div>{(actions || children) && <div className="head-actions">{actions || children}</div>}</div>;
}
export function WorkspaceTabs() {
  const { user } = useContext(AuthContext);
  const capabilities = useExpansion();
  const { pathname } = useLocation();
  const tabs = workspaceTabs(pathname, user?.role, capabilities);
  if (tabs.length < 2) return null;
  return <div className="segments core-subtabs workspace-tabs" role="navigation" aria-label="Chức năng trong nhóm">{tabs.map(tab => <Link key={tab.path} to={tab.path} className={tab.path === pathname ? 'active' : ''} aria-current={tab.path === pathname ? 'page' : undefined}>{tab.text}</Link>)}</div>;
}
export function ParkingIllustration() {
  return <svg viewBox="0 0 440 210" role="img" aria-label="Minh họa sơ đồ bãi đỗ xe"><rect x="12" y="16" width="416" height="180" rx="14" fill="#eaf1f8" /><path d="M12 107h416" stroke="#fff" strokeWidth="45" /><path d="M22 107h396" stroke="#b2c6d9" strokeDasharray="9 10" /><g stroke="#c0d1e1" fill="none" strokeWidth="2">{[55, 120, 185, 250, 315, 380].map(x => <path key={x} d={`M${x} 28v50m0 59v47`} />)}</g>{[[73, 28, '#3e80be'], [203, 28, '#a6c0d9'], [333, 28, '#417cad'], [138, 133, '#97b5cc'], [268, 133, '#2f71ad']].map(([x, y, color]) => <g key={x} transform={`translate(${x} ${y})`}><rect width="31" height="50" rx="9" fill={color} /><path d="M5 10h21l-2 8H7ZM7 35h17l2 7H5Z" fill="#e4eff9" /><path d="M2 17v15m27-15v15" stroke="#182f452f" strokeWidth="2" /></g>)}<path d="m210 101 8 6-8 6m8-6h-17" stroke="#88a9c5" strokeWidth="2" fill="none" /></svg>;
}
