import { useState, useContext, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import AuthContext from '../context/AuthContext';
import { Check } from 'lucide-react';
import './LoginPage.css';

export default function LoginPage() {
  const { login, register, token, setTokenDirectly } = useContext(AuthContext);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  
  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // Password strength calculation
  const calculateStrength = (pass) => {
    let score = 0;
    if (!pass) return 0;
    if (pass.length > 7) score += 1;
    if (/[A-Z]/.test(pass)) score += 1;
    if (/[0-9]/.test(pass)) score += 1;
    if (/[^A-Za-z0-9]/.test(pass)) score += 1;
    return score;
  };
  const strengthScore = calculateStrength(password);

  const hasLength = password.length >= 8;
  const hasUpper = /[A-Z]/.test(password);
  const hasNumber = /[0-9]/.test(password);
  const hasSpecial = /[^A-Za-z0-9]/.test(password);

  // Handle OAuth Callback
  useEffect(() => {
    const urlToken = searchParams.get('token');
    if (urlToken) {
      setTokenDirectly(urlToken);
      navigate('/analytics');
    }
  }, [searchParams, setTokenDirectly, navigate]);

  // Redirect if already logged in
  useEffect(() => {
    if (token) navigate('/analytics');
  }, [token, navigate]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setPasswordError('');
    setSubmitting(true);
    
    try {
      let result;
      if (isRegister) {
        if (password !== confirmPassword) {
          setSubmitting(false);
          return setPasswordError('Passwords do not match');
        }
        if (!hasLength || !hasUpper || !hasSpecial) {
          setSubmitting(false);
          return setPasswordError('Password must be at least 8 characters, and include 1 capital letter and 1 special character.');
        }
        result = await register(email, password);
      } else {
        result = await login(email, password);
      }

      if (result && result.success) {
        navigate('/analytics');
      } else {
        setError((result && result.error) || 'Authentication failed');
      }
    } catch (err) {
      setError(err.message || 'Authentication failed');
    } finally {
      setSubmitting(false);
    }
  };

  const handleGoogleLogin = () => {
    window.location.href = 'http://localhost:5000/api/auth/google';
  };

  const handleGithubLogin = () => {
    window.location.href = 'http://localhost:5000/api/auth/github';
  };

  return (
    <div className="ap-auth-page">
      <div className="ap-bg" aria-hidden="true" />
      
      <div className="ap-auth-container ap-anim-fade">
        <div className="ap-logo" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', marginBottom: '24px' }}>
          <svg viewBox="0 0 24 24" fill="none" className="ap-logo-svg" style={{ width: '28px', height: '28px', color: 'var(--text-1)' }}>
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          <span className="ap-logo-text" style={{ fontSize: '22px', color: 'var(--text-1)', fontWeight: 'bold', letterSpacing: '-0.5px' }}>Chorus</span>
        </div>
        
        <h1 className="ap-auth-title">{isRegister ? 'Create an account' : 'Welcome back'}</h1>
        <p className="ap-auth-subtitle">
          {isRegister ? 'Enter your details to register.' : 'Enter your credentials to access the platform.'}
        </p>

        {error && <div className="ap-auth-error">{error}</div>}

        <div className="ap-auth-oauth">
          <button type="button" className="ap-btn-oauth" onClick={handleGoogleLogin}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
            Continue with Google
          </button>
          <button type="button" className="ap-btn-oauth" onClick={handleGithubLogin}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg"><path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/></svg>
            Continue with GitHub
          </button>
        </div>

        <div className="ap-auth-divider">
          <span>or continue with email</span>
        </div>

        <form className="ap-auth-form" onSubmit={handleSubmit}>
          <div className="ap-form-group">
            <label htmlFor="email">Email address</label>
            <input 
              type="email" id="email" 
              value={email} onChange={e => setEmail(e.target.value)} 
              required placeholder="name@company.com" 
            />
          </div>
          
          <div className="ap-form-group">
            <label htmlFor="password">Password</label>
            <input 
              type="password" id="password" 
              value={password} onChange={e => { setPassword(e.target.value); setPasswordError(''); }} 
              required placeholder="••••••••" 
              style={passwordError ? { borderColor: 'var(--red)' } : {}}
            />
            {passwordError && <div className="ap-field-error">{passwordError}</div>}
            {isRegister && (
              <div className="ap-password-strength">
                <div className="ap-strength-track">
                  <div 
                    className="ap-strength-fill" 
                    data-score={strengthScore}
                    style={{ width: `${(strengthScore / 4) * 100}%` }}
                  />
                </div>
                <span className="ap-strength-text">
                  {strengthScore === 0 && 'Enter password'}
                  {strengthScore === 1 && 'Weak'}
                  {strengthScore === 2 && 'Fair'}
                  {strengthScore >= 3 && 'Strong'}
                </span>
              </div>
            )}
          </div>

          {isRegister && (
            <div className="ap-form-group">
              <label htmlFor="confirmPassword">Confirm Password</label>
              <input 
                type="password" id="confirmPassword" 
                value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} 
                required placeholder="••••••••" 
              />
            </div>
          )}

          <button type="submit" className="ap-btn-primary ap-btn-full" disabled={submitting}>
            {submitting ? 'Please wait...' : (isRegister ? 'Sign Up' : 'Sign In')}
          </button>
        </form>

        <p className="ap-auth-switch">
          {isRegister ? 'Already have an account?' : "Don't have an account?"}
          <button type="button" onClick={() => { setIsRegister(!isRegister); setError(''); setPasswordError(''); }}>
            {isRegister ? 'Sign in' : 'Sign up'}
          </button>
        </p>
      </div>
    </div>
  );
}
