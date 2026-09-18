const mongoose = require('mongoose');

const sceneSchema = new mongoose.Schema({
  scene_id: { type: Number },
  start: { type: Number },
  end: { type: Number },
  start_seconds: { type: Number },
  end_seconds: { type: Number },
  label: { type: String },
  event_type: { type: String },
  content: { type: String },
  source_agent: { type: String },
  confidence: { type: Number, default: 0.9 }
}, { _id: false });

const conflictSchema = new mongoose.Schema({
  scene_id: { type: Number },
  time_range: [{ type: Number }],
  source_a: { type: String },
  content_a: { type: String },
  source_b: { type: String },
  content_b: { type: String },
  conflict_type: { type: String }
}, { _id: false });

const caseSchema = new mongoose.Schema({
  case_id: {
    type: String,
    required: true,
    unique: true,
    index: true
  },
  title: {
    type: String,
    default: 'Untitled Video Case'
  },
  created_at: {
    type: Date,
    default: Date.now
  },
  sealed_at: {
    type: Date,
    default: null
  },
  status: {
    type: String,
    enum: ['sealed', 'processing', 'flagged'],
    default: 'sealed'
  },
  source_type: {
    type: String,
    default: 'local_upload'
  },
  playlist_total: {
    type: Number,
    default: null
  },
  raw_video_hash: {
    type: String,
    default: null
  },
  merkle_root: {
    type: String,
    default: null
  },
  artifact_count: {
    type: Number,
    default: 1
  },
  timestamp_authority: {
    type: String,
    default: 'rfc3161_freetsa'
  },
  analysis: {
    type: mongoose.Schema.Types.Mixed,
    default: {}
  },
  fused_timeline: [sceneSchema],
  conflicts: [conflictSchema],
  scenes_with_no_signal: [{ type: Number }],
  per_video_summaries: [{
    video_index: Number,
    title: String,
    summary: String,
    key_findings: [String],
    transcript_preview: String,
    url: String
  }],
  user_id: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User',
    default: null
  }
}, {
  timestamps: true
});

const MongooseCase = mongoose.model('Case', caseSchema);

// In-Memory store fallback when MongoDB is not connected
const inMemoryCases = [];

const CaseProxy = {
  find: async (query = {}) => {
    if (mongoose.connection.readyState === 1) {
      return MongooseCase.find(query).sort({ created_at: -1 });
    }
    return [...inMemoryCases];
  },

  findOne: async (query) => {
    if (mongoose.connection.readyState === 1) {
      return MongooseCase.findOne(query);
    }
    return inMemoryCases.find(c => c.case_id === query.case_id) || null;
  },

  findOneAndUpdate: async (filter, update, options = { new: true, upsert: true }) => {
    if (mongoose.connection.readyState === 1) {
      return MongooseCase.findOneAndUpdate(filter, update, options);
    }
    const idx = inMemoryCases.findIndex(c => c.case_id === filter.case_id);
    const updatedData = { ...update, ...filter };
    if (idx !== -1) {
      inMemoryCases[idx] = { ...inMemoryCases[idx], ...updatedData };
      return inMemoryCases[idx];
    } else {
      inMemoryCases.unshift(updatedData);
      return updatedData;
    }
  },

  create: async (data) => {
    if (mongoose.connection.readyState === 1) {
      return MongooseCase.create(data);
    }
    inMemoryCases.unshift(data);
    return data;
  }
};

module.exports = CaseProxy;
