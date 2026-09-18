const express = require('express');
const router = express.Router();
const User = require('../models/User');
const jwt = require('jsonwebtoken');
const passport = require('passport');
const { protect } = require('../middleware/auth');

// Helper function to issue JWT
const sendTokenResponse = (user, statusCode, res) => {
  const token = jwt.sign({ id: user._id }, process.env.JWT_SECRET, {
    expiresIn: '30d'
  });
  res.status(statusCode).json({ success: true, token });
};

// @route   POST /api/auth/register
// @desc    Register user
router.post('/register', async (req, res) => {
  try {
    const { email, password } = req.body;
    if (!email || !password) {
      return res.status(400).json({ success: false, error: 'Please provide email and password' });
    }
    const existingUser = await User.findOne({ email });
    if (existingUser) {
      return res.status(400).json({ success: false, error: 'Email already exists' });
    }
    const user = await User.create({ email, password });
    sendTokenResponse(user, 201, res);
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// @route   POST /api/auth/login
// @desc    Login user
router.post('/login', async (req, res) => {
  try {
    const { email, password } = req.body;
    if (!email || !password) {
      return res.status(400).json({ success: false, error: 'Please provide email and password' });
    }
    const user = await User.findOne({ email }).select('+password');
    if (!user) {
      return res.status(401).json({ success: false, error: 'Invalid credentials' });
    }
    const isMatch = await user.matchPassword(password);
    if (!isMatch) {
      return res.status(401).json({ success: false, error: 'Invalid credentials' });
    }
    sendTokenResponse(user, 200, res);
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// @route   GET /api/auth/me
// @desc    Get current logged in user
router.get('/me', protect, async (req, res) => {
  const user = await User.findById(req.user.id);
  if (!user) {
    return res.status(404).json({ success: false, error: 'User not found' });
  }
  const userObj = user.toObject ? user.toObject() : { ...user };
  if (!userObj.name) {
    userObj.name = (userObj.email && userObj.email.toLowerCase().includes('khush'))
      ? 'Khush Desai'
      : (userObj.email ? userObj.email.split('@')[0].replace(/[._-]/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) : 'Khush Desai');
  }
  res.status(200).json({ success: true, data: userObj });
});

// ==========================================
// OAUTH ROUTES
// ==========================================

// Helper for OAuth Redirects
const oauthRedirect = (req, res) => {
  // Generate a token for the OAuth user and redirect to frontend with token
  const token = jwt.sign({ id: req.user._id }, process.env.JWT_SECRET, { expiresIn: '30d' });
  // Redirect to frontend (in production, FRONTEND_URL is used)
  res.redirect(`${process.env.FRONTEND_URL || 'http://localhost:5173'}/auth/callback?token=${token}`);
};

const isGoogleConfigured = () =>
  Boolean(process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET && !process.env.GOOGLE_CLIENT_ID.includes('your_google_client_id'));

const isGithubConfigured = () =>
  Boolean(process.env.GITHUB_CLIENT_ID && process.env.GITHUB_CLIENT_SECRET && !process.env.GITHUB_CLIENT_ID.includes('your_github_client_id'));

// Google Auth
router.get('/google', (req, res, next) => {
  if (!isGoogleConfigured()) {
    return res.status(503).json({ success: false, error: 'Google OAuth is not configured on this server.' });
  }
  passport.authenticate('google', { scope: ['profile', 'email'] })(req, res, next);
});

router.get('/google/callback', (req, res, next) => {
  if (!isGoogleConfigured()) {
    return res.redirect(`${process.env.FRONTEND_URL || 'http://localhost:5173'}/login?error=Google+OAuth+not+configured`);
  }
  passport.authenticate('google', { failureRedirect: '/login', session: false })(req, res, next);
}, oauthRedirect);

// GitHub Auth
router.get('/github', (req, res, next) => {
  if (!isGithubConfigured()) {
    return res.status(503).json({ success: false, error: 'GitHub OAuth is not configured on this server.' });
  }
  passport.authenticate('github', { scope: ['user:email'] })(req, res, next);
});

router.get('/github/callback', (req, res, next) => {
  if (!isGithubConfigured()) {
    return res.redirect(`${process.env.FRONTEND_URL || 'http://localhost:5173'}/login?error=GitHub+OAuth+not+configured`);
  }
  passport.authenticate('github', { failureRedirect: '/login', session: false })(req, res, next);
}, oauthRedirect);

module.exports = router;

