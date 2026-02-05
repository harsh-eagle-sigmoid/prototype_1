import { useState, useEffect } from 'react';
import './App.css';
import { fetchHealth } from './api';
import MetricsPanel from './MetricsPanel';
import DriftPanel from './DriftPanel';
import ErrorsPanel from './ErrorsPanel';
import QueryPanel from './QueryPanel';
import ExecutionsPanel from './ExecutionsPanel';
import AlertsPanel from './AlertsPanel';
import AuthProvider, { LoginButton, RequireAuth, useAuth } from './AuthProvider';

const TABS = ['Metrics', 'Drift', 'Errors', 'Executions', 'Alerts'];

function Dashboard() {
  const [tab, setTab] = useState('Metrics');
  const [health, setHealth] = useState(null);
  const { authEnabled, user } = useAuth();

  // Poll health every 10 s
  useEffect(() => {
    const poll = () => fetchHealth().then(setHealth).catch(() => { });
    poll();
    const id = setInterval(poll, 3000);
    return () => clearInterval(id);
  }, []);

  const agentsUp = health
    ? Object.values(health.agents || {}).every(a => a.status === 'ok')
    : false;

  return (
    <div className="app-shell">
      {/* ── Navbar ── */}
      <nav className="navbar">
        <div className="brand">Unilever <span>Procurement GPT</span> — POC</div>
        <div className="tabs">
          {TABS.map(t => (
            <button key={t} className={`tab-btn ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>
              {t}
            </button>
          ))}
        </div>
        <div className="nav-right">
          <div className="nav-status">
            <span className={`status-dot ${agentsUp ? '' : 'down'}`} />
            {agentsUp ? 'All agents online' : 'Checking…'}
          </div>
          <LoginButton />
        </div>
      </nav>

      {/* ── Panel ── */}
      <main className="main-content">
        {tab === 'Metrics' && <MetricsPanel />}
        {tab === 'Drift' && <DriftPanel />}
        {tab === 'Errors' && <ErrorsPanel />}
        {tab === 'Executions' && <ExecutionsPanel />}
        {tab === 'Alerts' && <AlertsPanel />}
      </main>
    </div>
  );
}

// Main App with Auth Provider - RequireAuth blocks access until logged in
export default function App() {
  return (
    <AuthProvider>
      <RequireAuth>
        <Dashboard />
      </RequireAuth>
    </AuthProvider>
  );
}
