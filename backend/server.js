require('dotenv').config();
const express = require('express');
const cors = require('cors');
const passport = require('passport');
const session = require('express-session');
const connectDB = require('./config/db');

// Connect Database
connectDB();

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
app.use('/api/auth', require('./routes/auth'));
app.use('/api/cases', require('./routes/cases'));
app.use('/api/analyze', require('./routes/analyze'));
app.use('/api/videos', require('./routes/stream'));
app.use('/api/cyber', require('./routes/cyber'));
app.use('/api/review-queue', (req, res, next) => {
  req.url = '/review-queue' + (req.url === '/' ? '' : req.url);
  require('./routes/cyber')(req, res, next);
});

// Root route
app.get('/', (req, res) => {
  res.send('UNIVANCE API is running...');
});

const PORT = process.env.PORT || 5000;

app.listen(PORT, () => console.log(`Server running on port ${PORT}`));
