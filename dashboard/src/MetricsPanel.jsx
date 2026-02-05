import { useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { fetchMetrics } from './api';

export default function MetricsPanel() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  // Auto-refresh every 10 seconds
  useEffect(() => {
    const load = () => fetchMetrics().then(setData).catch(e => setError(e.message));
    load();  // Initial load
    const interval = setInterval(load, 3000);  // Poll every 3s
    return () => clearInterval(interval);
  }, []);

  if (error) return <p className="error-msg">{error}</p>;
  if (!data) return <p className="loading">Loading metrics...</p>;

  const { overall, per_agent } = data;

  // Bar chart data: one bar per agent
  const chartData = Object.entries(per_agent).map(([name, d]) => ({
    agent: name.charAt(0).toUpperCase() + name.slice(1),
    Accuracy: d.accuracy,
    AvgScore: +(d.avg_score * 100).toFixed(1),
  }));

  return (
    <>
      {/* Stat cards */}
      <div className="cards-row">
        <div className="card">
          <div className="label">Total Evaluated</div>
          <div className="value blue">{overall.total_evaluations}</div>
        </div>
        <div className="card">
          <div className="label">Passed</div>
          <div className="value green">{overall.passed}</div>
        </div>
        <div className="card">
          <div className="label">Failed</div>
          <div className="value red">{overall.failed}</div>
        </div>
        <div className="card">
          <div className="label">Accuracy</div>
          <div className={`value ${overall.accuracy >= 90 ? 'green' : 'orange'}`}>{overall.accuracy}%</div>
        </div>
        <div className="card">
          <div className="label">Avg Score</div>
          <div className="value blue">{overall.avg_score}</div>
        </div>
      </div>

      {/* Chart + per-agent table */}
      <div className="panels-row">
        <div className="panel">
          <h3>Accuracy by Agent</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={chartData} barGap={4}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a3548" />
              <XAxis dataKey="agent" stroke="#5a7a99" fontSize={13} />
              <YAxis domain={[0, 100]} stroke="#5a7a99" fontSize={12} unit="%" />
              <Tooltip contentStyle={{ background: '#1e2736', border: '1px solid #2a3548', borderRadius: 6, color: '#c8d6e5' }} />
              <Bar dataKey="Accuracy" fill="#4c9eff" radius={[4, 4, 0, 0]} />
              <Bar dataKey="AvgScore" fill="#3ecf8e" radius={[4, 4, 0, 0]} name="Avg Score %" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="panel">
          <h3>Per-Agent Breakdown</h3>
          <table className="data-table">
            <thead>
              <tr>
                <th>Agent</th><th>Total</th><th>Passed</th><th>Accuracy</th><th>Avg Score</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(per_agent).map(([name, d]) => (
                <tr key={name}>
                  <td style={{ textTransform: 'capitalize', fontWeight: 600, color: '#fff' }}>{name}</td>
                  <td>{d.total}</td>
                  <td style={{ color: '#3ecf8e' }}>{d.passed}</td>
                  <td><span className={`badge ${d.accuracy >= 90 ? 'low' : 'medium'}`}>{d.accuracy}%</span></td>
                  <td>{d.avg_score}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
