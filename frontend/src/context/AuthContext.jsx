import { createContext, useState, useEffect } from 'react';

export const API_BASE = 'http://localhost:5000';

const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
  const [token, setToken] = useState(localStorage.getItem('token'));
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // Load user on mount or when token changes
  useEffect(() => {
    const loadUser = async () => {
      if (!token) {
        setLoading(false);
        return;
      }
      try {
        const res = await fetch('http://localhost:5000/api/auth/me', {
          headers: { Authorization: `Bearer ${token}` }
        });
        const data = await res.json();
        if (data.success) {
          setUser(data.data);
          if (data.data?.name) {
            localStorage.setItem('chorus_user_name', data.data.name);
          } else if (data.data?.email && data.data.email.toLowerCase().includes('khush')) {
            localStorage.setItem('chorus_user_name', 'Khush Desai');
          }
          if (data.data?.email) {
            localStorage.setItem('chorus_user_email', data.data.email);
          }
        } else {
          setToken(null);
          localStorage.removeItem('token');
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    loadUser();
  }, [token]);

  const login = async (email, password) => {
    try {
      const res = await fetch('http://localhost:5000/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });
      const data = await res.json();
      if (data.success) {
        localStorage.setItem('token', data.token);
        if (email) {
          localStorage.setItem('chorus_user_email', email);
          if (email.toLowerCase().includes('khush')) {
            localStorage.setItem('chorus_user_name', 'Khush Desai');
          } else {
            const prefix = email.split('@')[0].replace(/[._-]/g, ' ');
            const formatted = prefix.replace(/\b\w/g, l => l.toUpperCase());
            localStorage.setItem('chorus_user_name', formatted);
          }
        }
        setToken(data.token);
        return { success: true };
      }
      return { success: false, error: data.error };
    } catch (err) {
      console.error('Login error:', err);
      return { success: false, error: 'Network error or backend is down' };
    }
  };

  const register = async (email, password) => {
    try {
      const res = await fetch('http://localhost:5000/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });
      const data = await res.json();
      if (data.success) {
        localStorage.setItem('token', data.token);
        if (email) {
          localStorage.setItem('chorus_user_email', email);
          if (email.toLowerCase().includes('khush')) {
            localStorage.setItem('chorus_user_name', 'Khush Desai');
          } else {
            const prefix = email.split('@')[0].replace(/[._-]/g, ' ');
            const formatted = prefix.replace(/\b\w/g, l => l.toUpperCase());
            localStorage.setItem('chorus_user_name', formatted);
          }
        }
        setToken(data.token);
        return { success: true };
      }
      return { success: false, error: data.error };
    } catch (err) {
      console.error('Registration error:', err);
      return { success: false, error: 'Network error or backend is down' };
    }
  };

  const logout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('chorus_user_email');
    localStorage.removeItem('chorus_user_name');
    localStorage.removeItem('chorus_user_avatar');
    setToken(null);
    setUser(null);
  };

  // For OAuth Callback handling
  const setTokenDirectly = (newToken) => {
    localStorage.setItem('token', newToken);
    setToken(newToken);
  };

  return (
    <AuthContext.Provider value={{ token, user, loading, login, register, logout, setTokenDirectly }}>
      {children}
    </AuthContext.Provider>
  );
};

export default AuthContext;
