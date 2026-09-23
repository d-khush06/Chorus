require('dotenv').config();
const express = require('express');
const cors = require('cors');
const passport = require('passport');
const session = require('express-session');
const connectDB = require('./config/db');
const { performHealthCheck } = require('./services/rtspHealthCheck');

// Connect Database
connectDB();

// Run startup RTSP health check
performHealthCheck();

const app = express();

// Body parser
app.use(express.json());

// Enable CORS
app.use(cors());

// Express Session (required for Passport OAuth state)
app.use(session({
  secret: process.env.SESSION_SECRET || 'secret',
  resave: false,
  saveUninitialized: false
}));

// Passport config & middleware
require('./config/passport')(passport);
app.use(passport.initialize());
app.use(passport.session());

// Mount routers
app.use('/api/auth',         require('./routes/auth'));
app.use('/api/cases',        require('./routes/cases'));
app.use('/api/analyze',      require('./routes/analyze'));
app.use('/api/videos',       require('./routes/stream'));
app.use('/api/cyber',        require('./routes/cyber'));
app.use('/api/tunnel',       require('./routes/tunnel'));  // Cloudflare / public-IP CCTV tunnels
app.use('/api/review-queue', (req, res, next) => {
  req.url = '/review-queue' + (req.url === '/' ? '' : req.url);
  require('./routes/cyber')(req, res, next);
});

// Root route
app.get('/', (req, res) => {
  res.send('UNIVANCE API is running...');
});

const PORT = process.env.PORT || 5000;

const server = app.listen(PORT, () => console.log(`Server running on port ${PORT}`));

// Graceful shutdown — stop all cloudflare tunnels cleanly
const shutdown = () => {
  console.log('[Server] Shutting down — stopping active tunnels...');
  try {
    const { getCloudflareService } = require('./services/cloudflareService');
    getCloudflareService().stopAll();
  } catch (_) {}
  server.close(() => process.exit(0));
};
process.on('SIGTERM', shutdown);
process.on('SIGINT',  shutdown);

