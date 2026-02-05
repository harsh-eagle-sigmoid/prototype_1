import { useState, useEffect } from 'react';
import { fetchHistory } from './api';

export default function ExecutionsPanel() {
    const [runs, setRuns] = useState([]);
    const [loading, setLoading] = useState(true);
    const [searchTerm, setSearchTerm] = useState('');

    useEffect(() => {
        loadHistory();
        const interval = setInterval(loadHistory, 3000); // Poll every 3s
        return () => clearInterval(interval);
    }, []);

    const loadHistory = () => {
        fetchHistory()
            .then(data => {
                setRuns(data);
                setLoading(false);
            })
            .catch(err => {
                console.error("Failed to load history", err);
                setLoading(false);
            });
    };

    const filteredRuns = runs.filter(run =>
        (run.prompt || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
        (run.dataset || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
        (run.correctness_verdict || '').toLowerCase().includes(searchTerm.toLowerCase())
    );

    return (
        <div className="panel">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h2 style={{ margin: 0, fontSize: '1rem', color: '#5a7a99', textTransform: 'uppercase', letterSpacing: '0.8px' }}>Execution Runs</h2>
                <span className="refresh-info" style={{ fontSize: '0.8rem', color: '#7a8fa3' }}>Auto-refreshing</span>
            </div>

            <div style={{ marginBottom: '16px' }}>
                <input
                    type="text"
                    placeholder="Search query, dataset, or status..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    style={{
                        width: '100%',
                        padding: '10px 14px',
                        background: '#1a2232',
                        border: '1px solid #2a3548',
                        borderRadius: '6px',
                        color: '#fff',
                        outline: 'none',
                        fontSize: '0.9rem'
                    }}
                />
            </div>

            <div className="table-wrapper" style={{ overflowX: 'auto', maxHeight: '500px', overflowY: 'auto', border: '1px solid #2a3548', borderRadius: '6px' }}>
                <table className="data-table" style={{ width: '100%', borderCollapse: 'collapse', margin: 0 }}>
                    <thead style={{ position: 'sticky', top: 0, backgroundColor: '#1e293b', zIndex: 5 }}>
                        <tr>
                            <th>Prompt</th>
                            <th>Correctness</th>
                            <th>Drift Level</th>
                            <th>Confidence</th>
                            <th>Error Bucket</th>
                            <th>Dataset</th>
                            <th>Timestamp</th>
                        </tr>
                    </thead>
                    <tbody>
                        {loading && runs.length === 0 ? (
                            <tr><td colSpan="6" style={{ padding: '20px', textAlign: 'center' }}>Loading...</td></tr>
                        ) : filteredRuns.map((run, i) => (
                            <tr key={run.query_id || i}>
                                <td style={{ maxWidth: '300px' }} title={run.prompt}>
                                    {run.prompt}
                                </td>
                                <td>
                                    <span className={`badge ${run.correctness_verdict === 'PASS' ? 'low' : (run.correctness_verdict === 'FAIL' ? 'critical' : 'medium')}`}>
                                        {run.correctness_verdict}
                                    </span>
                                </td>
                                <td>
                                    <span className={`badge ${run.drift_level === 'normal' ? 'low' : run.drift_level}`}>
                                        {run.drift_level}
                                    </span>
                                    {run.drift_level !== 'N/A' && (
                                        <span style={{ marginLeft: '6px', fontSize: '0.8em', color: '#7a8fa3' }}>
                                            {Number(run.drift_score).toFixed(2)}
                                        </span>
                                    )}
                                </td>
                                <td>
                                    {(run.evaluation_confidence * 100).toFixed(1)}%
                                </td>
                                <td>
                                    {run.error_bucket !== 'None' ? (
                                        <span style={{ color: '#ff6b6b' }}>{run.error_bucket}</span>
                                    ) : (
                                        <span style={{ color: '#5a7a99' }}>-</span>
                                    )}
                                </td>
                                <td>
                                    <span style={{ color: run.dataset.toLowerCase() === 'spend' ? '#4c9eff' : '#f7b731', fontWeight: 600 }}>
                                        {run.dataset.toUpperCase()}
                                    </span>
                                </td>
                                <td style={{ color: '#7a8fa3', fontSize: '0.85em' }}>
                                    {new Date(run.timestamp).toLocaleString()}
                                </td>
                            </tr>
                        ))}
                        {!loading && filteredRuns.length === 0 && (
                            <tr><td colSpan="6" style={{ padding: '20px', textAlign: 'center', color: '#7a8fa3' }}>No matching runs found.</td></tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
