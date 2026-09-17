const mongoose = require('mongoose');
const bcrypt = require('bcryptjs');

const userSchema = new mongoose.Schema({
  email: {
    type: String,
    required: false, // Optional if signing in with OAuth
    unique: true,
    sparse: true,
    match: [
      /^\w+([.-]?\w+)*@\w+([.-]?\w+)*(\.\w{2,3})+$/,
      'Please add a valid email'
    ]
  },
  password: {
    type: String,
    required: false, // Not needed for OAuth users
    minlength: 6,
    select: false // Exclude password from query results by default
  },
  googleId: {
    type: String,
    unique: true,
    sparse: true
  },
  githubId: {
    type: String,
    unique: true,
    sparse: true
  },
  role: {
    type: String,
    enum: ['user', 'admin'],
    default: 'user'
  },
  createdAt: {
    type: Date,
    default: Date.now
  }
});

// Encrypt password using bcrypt
userSchema.pre('save', async function () {
  // Only hash if password is provided and modified
  if (!this.isModified('password') || !this.password) {
    return;
  }
  const salt = await bcrypt.genSalt(10);
  this.password = await bcrypt.hash(this.password, salt);
});

// Match user entered password to hashed password in database
userSchema.methods.matchPassword = async function (enteredPassword) {
  if (!this.password) return false;
  return await bcrypt.compare(enteredPassword, this.password);
};

const MongooseUser = mongoose.model('User', userSchema);

// In-Memory store fallback when MongoDB Atlas is unreachable
const inMemoryUsers = [];
let nextId = 1;

class InMemoryUser {
  constructor(data) {
    this._id = 'user_' + (nextId++);
    this.email = data.email;
    this.password = data.password;
    this.googleId = data.googleId;
    this.githubId = data.githubId;
    this.role = data.role || 'user';
    this.createdAt = new Date();
  }

  async matchPassword(enteredPassword) {
    if (!this.password) return false;
    return await bcrypt.compare(enteredPassword, this.password);
  }

  async save() {
    const idx = inMemoryUsers.findIndex(u => u._id === this._id);
    if (idx !== -1) {
      inMemoryUsers[idx] = this;
    } else {
      inMemoryUsers.push(this);
    }
    return this;
  }
}

const UserProxy = {
  findOne: (query) => {
    if (mongoose.connection.readyState === 1) {
      return MongooseUser.findOne(query);
    }
    const execute = async () => {
      const found = inMemoryUsers.find(u => {
        if (query.email && u.email && u.email.toLowerCase() === query.email.toLowerCase()) return true;
        if (query.googleId && u.googleId === query.googleId) return true;
        if (query.githubId && u.githubId === query.githubId) return true;
        return false;
      });
      return found || null;
    };
    const promise = execute();
    promise.select = () => promise;
    return promise;
  },

  findById: async (id) => {
    if (mongoose.connection.readyState === 1) {
      return MongooseUser.findById(id);
    }
    const found = inMemoryUsers.find(u => u._id === (id ? id.toString() : ''));
    return found || null;
  },

  create: async (data) => {
    if (mongoose.connection.readyState === 1) {
      return MongooseUser.create(data);
    }
    let hashedPassword = data.password;
    if (hashedPassword) {
      const salt = await bcrypt.genSalt(10);
      hashedPassword = await bcrypt.hash(hashedPassword, salt);
    }
    const user = new InMemoryUser({ ...data, password: hashedPassword });
    await user.save();
    return user;
  }
};

module.exports = UserProxy;
