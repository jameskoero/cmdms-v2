import axios from 'axios';

const BASE_URL = process.env.REACT_APP_API_URL || '/api';

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' }
});

// Attach token to every request
api.interceptors.request.use(config => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 - try refresh, else logout
api.interceptors.response.use(
  res => res,
  async error => {
    const original = error.config;
    if (
      error.response?.status === 401 &&
      !original._retry &&
      original.url !== '/auth/login'
    ) {
      original._retry = true;
      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken) {
        try {
          const res = await axios.post(`${BASE_URL}/auth/refresh`, {}, {
            headers: { Authorization: `Bearer ${refreshToken}` }
          });
          const newToken = res.data.access_token;
          localStorage.setItem('access_token', newToken);
          original.headers.Authorization = `Bearer ${newToken}`;
          return api(original);
        } catch {
          // Refresh failed - clear and redirect
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          localStorage.removeItem('user');
          window.location.href = '/login';
        }
      } else {
        localStorage.removeItem('access_token');
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

// ─── AUTH ─────────────────────────────────────────────
export const authAPI = {
  login: (credentials) => api.post('/auth/login', credentials),
  me: () => api.get('/auth/me'),
  changePassword: (data) => api.post('/auth/change-password', data),
};

// ─── MEMBERS ──────────────────────────────────────────
export const membersAPI = {
  getAll: (params) => api.get('/members/', { params }),
  getOne: (id) => api.get(`/members/${id}`),
  create: (data) => api.post('/members/', data),
  update: (id, data) => api.put(`/members/${id}`, data),
  delete: (id) => api.delete(`/members/${id}`),
  getSummary: () => api.get('/members/stats/summary'),
  getCellGroups: () => api.get('/members/cell-groups'),
};

// ─── ATTENDANCE ───────────────────────────────────────
export const attendanceAPI = {
  getAll: (params) => api.get('/attendance/', { params }),
  create: (data) => api.post('/attendance/', data),
  delete: (id) => api.delete(`/attendance/${id}`),
  getServiceTypes: () => api.get('/attendance/service-types'),
  getSummary: () => api.get('/attendance/stats/summary'),
};

// ─── FINANCE ──────────────────────────────────────────
export const financeAPI = {
  getAll: (params) => api.get('/finance/', { params }),
  create: (data) => api.post('/finance/', data),
  update: (id, data) => api.put(`/finance/${id}`, data),
  delete: (id) => api.delete(`/finance/${id}`),
  getSummary: (params) => api.get('/finance/summary', { params }),
  getTransactionTypes: () => api.get('/finance/transaction-types'),
  getCategories: () => api.get('/finance/categories'),
};

// ─── EVENTS ───────────────────────────────────────────
export const eventsAPI = {
  getAll: (params) => api.get('/events/', { params }),
  getUpcoming: () => api.get('/events/upcoming'),
  getOne: (id) => api.get(`/events/${id}`),
  create: (data) => api.post('/events/', data),
  update: (id, data) => api.put(`/events/${id}`, data),
  delete: (id) => api.delete(`/events/${id}`),
};

// ─── USERS ────────────────────────────────────────────
export const usersAPI = {
  getAll: () => api.get('/users/'),
  create: (data) => api.post('/users/', data),
  update: (id, data) => api.put(`/users/${id}`, data),
  delete: (id) => api.delete(`/users/${id}`),
  getRoles: () => api.get('/users/roles'),
};

// ─── DASHBOARD ────────────────────────────────────────
export const dashboardAPI = {
  getStats: () => api.get('/dashboard/stats'),
};

export default api;
