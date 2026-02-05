import axios from 'axios';

const BASE = '/api/v1';

// Create axios instance with interceptors
const api = axios.create();

// Token storage (set from AuthProvider)
let accessToken = null;

export const setAccessToken = (token) => {
  accessToken = token;
};

// Add auth header to requests when token is available
api.interceptors.request.use((config) => {
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

// API calls
export const fetchHealth = () => api.get('/health').then(r => r.data);
export const fetchMetrics = () => api.get(`${BASE}/metrics`).then(r => r.data);
export const fetchDrift = (agentType) => api.get(`${BASE}/drift`, { params: agentType ? { agent_type: agentType } : {} }).then(r => r.data);
export const fetchErrors = (category) => api.get(`${BASE}/errors`, { params: category ? { category } : {} }).then(r => r.data);
export const fetchErrorsByCategory = (category) => api.get(`${BASE}/errors/${category}`).then(r => r.data);
export const sendQuery = (query, agentType) => api.post(`${BASE}/query`, { query, agent_type: agentType }).then(r => r.data);
export const fetchUserInfo = () => api.get(`${BASE}/auth/me`).then(r => r.data);
export const fetchHistory = (limit = 50) => api.get(`${BASE}/history`, { params: { limit } }).then(r => r.data);
export const fetchAlerts = () => api.get(`${BASE}/alerts`).then(r => r.data);
export const executeSql = (sql, agentType) => api.post(`${BASE}/debug/execute`, { sql, agent_type: agentType }).then(r => r.data);
