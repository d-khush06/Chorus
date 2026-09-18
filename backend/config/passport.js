const GoogleStrategy = require('passport-google-oauth20').Strategy;
const GitHubStrategy = require('passport-github2').Strategy;
const User = require('../models/User');

module.exports = function(passport) {
  // Google OAuth Strategy
  if (process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET && !process.env.GOOGLE_CLIENT_ID.includes('your_google_client_id')) {
    passport.use(
      new GoogleStrategy(
        {
          clientID: process.env.GOOGLE_CLIENT_ID,
          clientSecret: process.env.GOOGLE_CLIENT_SECRET,
          callbackURL: process.env.GOOGLE_CALLBACK_URL || 'http://localhost:5000/api/auth/google/callback',
        },
        async (accessToken, refreshToken, profile, done) => {
          try {
            let user = await User.findOne({ googleId: profile.id });
            if (user) {
              return done(null, user);
            }

            const email = profile.emails && profile.emails[0].value;
            if (email) {
              user = await User.findOne({ email });
              if (user) {
                user.googleId = profile.id;
                await user.save();
                return done(null, user);
              }
            }

            user = await User.create({
              googleId: profile.id,
              email: email || undefined
            });

            done(null, user);
          } catch (err) {
            console.error(err);
            done(err, false);
          }
        }
      )
    );
  } else {
    console.warn('[Passport] Google OAuth credentials not configured. Google OAuth login disabled.');
  }

  // GitHub OAuth Strategy
  if (process.env.GITHUB_CLIENT_ID && process.env.GITHUB_CLIENT_SECRET && !process.env.GITHUB_CLIENT_ID.includes('your_github_client_id')) {
    passport.use(
      new GitHubStrategy(
        {
          clientID: process.env.GITHUB_CLIENT_ID,
          clientSecret: process.env.GITHUB_CLIENT_SECRET,
          callbackURL: process.env.GITHUB_CALLBACK_URL || 'http://localhost:5000/api/auth/github/callback',
          scope: ['user:email']
        },
        async (accessToken, refreshToken, profile, done) => {
          try {
            let user = await User.findOne({ githubId: profile.id });
            if (user) {
              return done(null, user);
            }

            const email = profile.emails && profile.emails[0].value;
            if (email) {
              user = await User.findOne({ email });
              if (user) {
                user.githubId = profile.id;
                await user.save();
                return done(null, user);
              }
            }

            user = await User.create({
              githubId: profile.id,
              email: email || undefined
            });

            done(null, user);
          } catch (err) {
            console.error(err);
            done(err, false);
          }
        }
      )
    );
  } else {
    console.warn('[Passport] GitHub OAuth credentials not found. GitHub OAuth login disabled.');
  }

  // Serialize / Deserialize User (needed by Passport session even if mostly JWT driven during OAuth flow)
  passport.serializeUser((user, done) => {
    done(null, user.id);
  });
  
  passport.deserializeUser(async (id, done) => {
    try {
      const user = await User.findById(id);
      done(null, user);
    } catch (err) {
      done(err, null);
    }
  });
};
