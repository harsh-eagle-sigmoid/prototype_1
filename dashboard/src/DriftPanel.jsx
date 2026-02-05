import { useEffect, useState } from 'react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts';
import { fetchDrift, executeSql } from './api';

const COLORS = { normal: '#3ecf8e', medium: '#f7b731', high: '#ff6b6b' };

export default function DriftPanel() {
  const [data, setData] = useState(null);
  const [filter, setFilter] = useState('');
  const [error, setError] = useState(null);
  const [selectedQuery, setSelectedQuery] = useState(null);

  // Execution State
  const [execResult, setExecResult] = useState(null);
  const [execLoading, setExecLoading] = useState(false);

  const load = (agentType) => {
    fetchDrift(agentType || undefined)
      .then(setData)
      .catch(e => setError(e.message));
  };

  useEffect(() => {
    load(filter);
    const interval = setInterval(() => load(filter), 3000);
    return () => clearInterval(interval);
  }, [filter]);

  // Auto-load output when query selected
  useEffect(() => {
    if (!selectedQuery?.sql || !selectedQuery?.agent_type) {
      setExecResult(null);
      return;
    }

    // If no SQL, skip
    if (selectedQuery.sql.includes("Not Available")) {
      setExecResult({ status: 'error', error: 'No SQL recorded.' });
      return;
    }

    setExecLoading(true);
    // Simulating "fetching static output" by re-executing
    executeSql(selectedQuery.sql, selectedQuery.agent_type)
      .then(res => setExecResult(res))
      .catch(err => setExecResult({ status: 'error', error: err.message }))
      .finally(() => setExecLoading(false));

  }, [selectedQuery]);

  if (error) return <p className="error-msg">{error}</p>;
  if (!data) return <p className="loading">Loading drift data...</p>;

  const { distribution, total_anomalies, high_drift_samples } = data;
  const pieData = Object.entries(distribution).map(([name, d]) => ({
    name: name.charAt(0).toUpperCase() + name.slice(1),
    value: d.count, key: name,
  }));

  return (
    <>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 18, flexWrap: 'wrap' }}>
        {['', 'spend', 'demand'].map(v => (
          <button key={v} className={`tab-btn ${filter === v ? 'active' : ''}`} onClick={() => setFilter(v)}>
            {v || 'All'}
          </button>
        ))}
      </div>

      <div className="cards-row">
        <div className="card"><div className="label">Total Monitored</div><div className="value blue">{pieData.reduce((s, d) => s + d.value, 0)}</div></div>
        <div className="card"><div className="label">Anomalies</div><div className="value red">{total_anomalies}</div></div>
        <div className="card"><div className="label">Normal</div><div className="value green">{distribution.normal?.count || 0}</div></div>
        <div className="card"><div className="label">Medium Drift</div><div className="value orange">{distribution.medium?.count || 0}</div></div>
        <div className="card"><div className="label">High Drift</div><div className="value red">{distribution.high?.count || 0}</div></div>
      </div>

      <div className="panels-row">
        <div className="panel">
          <h3>Drift Distribution</h3>
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90} label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`} labelLine={false}>
                {pieData.map((entry) => <Cell key={entry.key} fill={COLORS[entry.key] || '#7a8fa3'} />)}
              </Pie>
              <Tooltip contentStyle={{ background: '#1e2736', border: '1px solid #2a3548', borderRadius: 6, color: '#c8d6e5' }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="panel">
          <h3>Avg Drift Score by Level</h3>
          <table className="data-table">
            <thead><tr><th>Level</th><th>Count</th><th>Avg Score</th></tr></thead>
            <tbody>
              {Object.entries(distribution).map(([lvl, d]) => (
                <tr key={lvl}>
                  <td><span className={`badge ${lvl}`}>{lvl}</span></td>
                  <td>{d.count}</td>
                  <td>{d.avg_drift_score}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel" style={{ marginBottom: '24px' }}>
        <h3>Top High-Drift Queries (Select to view details)</h3>
        <div style={{ maxHeight: '400px', overflowY: 'auto', border: '1px solid #334155', borderRadius: '6px' }}>
          <table className="data-table" style={{ margin: 0 }}>
            <thead style={{ position: 'sticky', top: 0, backgroundColor: '#1e293b', zIndex: 5 }}>
              <tr><th>Query</th><th>Query ID</th><th>Drift Score</th><th>Level</th></tr>
            </thead>
            <tbody>
              {high_drift_samples.map((s, i) => (
                <tr key={i} onClick={() => setSelectedQuery(s)}
                  style={{ cursor: 'pointer', backgroundColor: selectedQuery?.query_id === s.query_id ? 'rgba(76, 158, 255, 0.1)' : 'transparent', transition: 'background 0.2s' }}>
                  <td style={{ color: '#e2e8f0', maxWidth: '300px' }}>{s.query_text}</td>
                  <td className="mono" style={{ fontSize: '0.85em', color: '#94a3b8' }}>{s.query_id}</td>
                  <td style={{ color: '#ff6b6b', fontWeight: 600 }}>{s.drift_score}</td>
                  <td><span className="badge high">{s.classification}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {selectedQuery && (
        <div className="panel" style={{ borderTop: '4px solid #4c9eff', animation: 'fadeIn 0.3s' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h3>Query Details</h3>
            <button onClick={() => setSelectedQuery(null)} style={{ background: 'none', border: 'none', color: '#7a8fa3', cursor: 'pointer' }}>✕ Close</button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: '24px' }}>
            <div>
              <div className="label">Natural Language Query</div>
              <div style={{ padding: '12px', background: '#0f1420', borderRadius: '6px', color: '#fff', fontSize: '1.1rem', marginBottom: '16px' }}>
                {selectedQuery.query_text}
              </div>
              <div className="label">Generated SQL</div>
              <pre style={{ padding: '12px', background: '#0f1420', borderRadius: '6px', color: '#8ecae6', overflowX: 'auto', fontFamily: 'Consolas, monospace', fontSize: '0.85rem', whiteSpace: 'pre-wrap' }}>
                {selectedQuery.sql}
              </pre>
            </div>

            <div>
              <div className="label">Query Output</div>
              <div style={{ background: '#0f1420', padding: '16px', borderRadius: '6px', minHeight: '150px' }}>
                {execLoading ? (
                  <div style={{ color: '#5a7a99', fontStyle: 'italic', padding: '20px' }}>Loading output...</div>
                ) : !execResult ? (
                  <div style={{ color: '#7a8fa3' }}>No output data.</div>
                ) : execResult.status === 'error' ? (
                  <div style={{ color: '#ff6b6b', fontFamily: 'monospace' }}>{execResult.error}</div>
                ) : execResult.results.length === 0 ? (
                  <div style={{ color: '#7a8fa3', fontStyle: 'italic' }}>0 rows returned.</div>
                ) : (
                  <div style={{ overflowX: 'auto', maxHeight: '300px' }}>
                    <table className="data-table">
                      <thead>
                        <tr>{Object.keys(execResult.results[0]).map(k => <th key={k}>{k}</th>)}</tr>
                      </thead>
                      <tbody>
                        {execResult.results.map((row, idx) => (
                          <tr key={idx}>{Object.values(row).map((v, i) => <td key={i}>{String(v)}</td>)}</tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
