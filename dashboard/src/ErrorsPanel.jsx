import { useEffect, useState } from 'react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts';
import { fetchErrors } from './api';

const CAT_COLORS = {
  SQL_GENERATION: '#ff6b6b',
  SQL_GENERATION_ERROR: '#ff9a9a',
  CONTEXT_RETRIEVAL: '#f7b731',
  DATA_ERROR: '#4c9eff',
  INTEGRATION: '#a55eea',
  AGENT_LOGIC: '#3ecf8e',
};

export default function ErrorsPanel() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  // Auto-refresh every 10 seconds
  useEffect(() => {
    const load = () => fetchErrors().then(setData).catch(e => setError(e.message));
    load();  // Initial load
    const interval = setInterval(load, 3000);
    return () => clearInterval(interval);
  }, []);

  if (error) return <p className="error-msg">{error}</p>;
  if (!data) return <p className="loading">Loading errors...</p>;

  const { total_errors, categories, recent_errors } = data;

  const pieData = Object.entries(categories).map(([name, d]) => ({
    name, value: d.count
  }));

  return (
    <>
      {/* Cards */}
      <div className="cards-row">
        <div className="card">
          <div className="label">Total Errors</div>
          <div className="value red">{total_errors}</div>
        </div>
        {Object.entries(categories).map(([cat, d]) => (
          <div className="card" key={cat}>
            <div className="label">{cat.replace(/_/g, ' ')}</div>
            <div className="value orange">{d.count}</div>
          </div>
        ))}
      </div>

      <div className="panels-row">
        {/* Pie */}
        <div className="panel">
          <h3>Error Category Distribution</h3>
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={85}
                label={({ name, percent }) => `${name.replace(/_/g, ' ')} ${(percent * 100).toFixed(0)}%`}
                labelLine={false} fontSize={11}>
                {pieData.map((entry) => (
                  <Cell key={entry.name} fill={CAT_COLORS[entry.name] || '#7a8fa3'} />
                ))}
              </Pie>
              <Tooltip contentStyle={{ background: '#1e2736', border: '1px solid #2a3548', borderRadius: 6, color: '#c8d6e5' }} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Category summary table */}
        <div className="panel">
          <h3>Category Breakdown</h3>
          <table className="data-table">
            <thead><tr><th>Category</th><th>Count</th><th>Severity</th></tr></thead>
            <tbody>
              {Object.entries(categories).map(([cat, d]) => (
                <tr key={cat}>
                  <td style={{ fontWeight: 600, color: '#fff', fontSize: '0.82rem' }}>{cat.replace(/_/g, ' ')}</td>
                  <td>{d.count}</td>
                  <td>
                    {Object.entries(d.severities).map(([sev, cnt]) => (
                      <span key={sev} className={`badge ${sev.toLowerCase()}`} style={{ marginRight: 4 }}>{sev} ({cnt})</span>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Recent errors full-width */}
      <div className="panel" style={{ marginTop: 0 }}>
        <h3>Recent Errors</h3>
        <div style={{ overflowX: 'auto', maxHeight: '500px', overflowY: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Query ID</th>
                <th>Query</th>
                <th>Category</th>
                <th>Severity</th>
                <th>Message</th>
              </tr>
            </thead>
            <tbody>
              {recent_errors.map((e, i) => (
                <tr key={i}>
                  <td className="mono" style={{ whiteSpace: 'nowrap' }}>{e.query_id}</td>
                  <td style={{ color: '#b0c4d8', fontSize: '0.82rem', maxWidth: '250px' }} title={e.query_text}>
                    {e.query_text}
                  </td>
                  <td style={{ color: '#fff', fontWeight: 600, fontSize: '0.82rem', whiteSpace: 'nowrap' }}>
                    {e.category.replace(/_/g, ' ')}
                  </td>
                  <td><span className={`badge ${e.severity.toLowerCase()}`}>{e.severity}</span></td>
                  <td style={{ maxWidth: 400, wordBreak: 'break-word' }}>
                    {e.message.slice(0, 100)}{e.message.length > 100 ? '…' : ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
