const mongoose = require('mongoose');

let isMongoConnected = false;

const connectDB = async () => {
  try {
    const conn = await mongoose.connect(process.env.MONGO_URI, {
      serverSelectionTimeoutMS: 2500
    });
    isMongoConnected = true;
    console.log(`MongoDB Connected: ${conn.connection.host}`);
  } catch (err) {
    isMongoConnected = false;
    console.warn(`[MongoDB Warning] Could not connect to MongoDB Atlas (${err.message}).`);
    console.warn(`[Fallback] Using resilient in-memory authentication storage.`);
  }
};

module.exports = connectDB;
module.exports.isMongoConnected = () => isMongoConnected;
