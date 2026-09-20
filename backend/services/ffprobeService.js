const { spawn } = require('child_process');
const path = require('path');

function runFFprobe(filePath) {
  return new Promise((resolve, reject) => {
    const ffprobePath = process.env.FFPROBE_PATH || 'ffprobe';
    const args = [
      '-v', 'quiet',
      '-print_format', 'json',
      '-show_format',
      '-show_streams',
      '-show_entries', 'format=format_name,format_long_name,bit_rate,creation_time,encoder:stream=codec_name,codec_long_name,codec_type,width,height,r_frame_rate,avg_frame_rate,bit_rate,disposition,tags',
      filePath
    ];

    const proc = spawn(ffprobePath, args, { windowsHide: true });

    let stdout = '';
    let stderr = '';

    proc.stdout.on('data', (data) => {
      stdout += data.toString('utf-8');
    });

    proc.stderr.on('data', (data) => {
      stderr += data.toString('utf-8');
    });

    proc.on('close', (code) => {
      if (code !== 0) {
        return reject(new Error(`ffprobe failed (code ${code}): ${stderr}`));
      }
      try {
        const data = JSON.parse(stdout);
        resolve(parseFFprobeOutput(data));
      } catch (err) {
        reject(new Error(`Failed to parse ffprobe output: ${err.message}`));
      }
    });

    proc.on('error', (err) => {
      reject(new Error(`ffprobe spawn error: ${err.message}`));
    });
  });
}

function parseFFprobeOutput(data) {
  const format = data.format || {};
  const streams = data.streams || [];

  const videoStream = streams.find(s => s.codec_type === 'video');
  const audioStream = streams.find(s => s.codec_type === 'audio');

  const result = {
    container: {
      format_name: format.format_name,
      format_long_name: format.format_long_name,
      bit_rate: format.bit_rate ? parseInt(format.bit_rate, 10) : null,
      creation_time: format.tags?.creation_time || null,
      encoder: format.tags?.encoder || null,
      duration: format.duration ? parseFloat(format.duration) : null,
      size: format.size ? parseInt(format.size, 10) : null
    },
    video: videoStream ? {
      codec_name: videoStream.codec_name,
      codec_long_name: videoStream.codec_long_name,
      width: videoStream.width,
      height: videoStream.height,
      r_frame_rate: videoStream.r_frame_rate,
      avg_frame_rate: videoStream.avg_frame_rate,
      bit_rate: videoStream.bit_rate ? parseInt(videoStream.bit_rate, 10) : null,
      disposition: videoStream.disposition || {},
      tags: videoStream.tags || {}
    } : null,
    audio: audioStream ? {
      codec_name: audioStream.codec_name,
      codec_long_name: audioStream.codec_long_name,
      sample_rate: audioStream.sample_rate,
      channels: audioStream.channels,
      bit_rate: audioStream.bit_rate ? parseInt(audioStream.bit_rate, 10) : null,
      disposition: audioStream.disposition || {},
      tags: audioStream.tags || {}
    } : null,
    editing_software_traces: detectEditingTraces(format, streams)
  };

  return result;
}

function detectEditingTraces(format, streams) {
  const traces = [];
  const tags = { ...(format.tags || {}) };
  
  for (const stream of streams) {
    if (stream.tags) {
      Object.assign(tags, stream.tags);
    }
  }

  const knownEditors = [
    'Adobe Premiere', 'Final Cut', 'DaVinci Resolve', 'Avid', 'Vegas',
    'HandBrake', 'FFmpeg', 'Lavf', 'x264', 'x265', 'MediaCoder',
    'iMovie', 'Windows Movie Maker', 'Camtasia', 'ScreenFlow'
  ];

  for (const [key, value] of Object.entries(tags)) {
    const valStr = String(value).toLowerCase();
    for (const editor of knownEditors) {
      if (valStr.includes(editor.toLowerCase())) {
        traces.push({ field: key, value, detected_editor: editor });
      }
    }
  }

  if (tags.encoder && !tags.encoder.toLowerCase().includes('hardware')) {
    traces.push({ field: 'encoder', value: tags.encoder, note: 'Software encoding detected' });
  }

  return traces.length > 0 ? traces : [{ note: 'No obvious editing software traces detected' }];
}

function generatePreview(inputPath, outputPath) {
  return new Promise((resolve, reject) => {
    const ffmpegPath = process.env.FFMPEG_PATH || 'ffmpeg';
    const args = [
      '-y',
      '-i', inputPath,
      '-c:v', 'libx264',
      '-preset', 'fast',
      '-crf', '23',
      '-c:a', 'aac',
      '-b:a', '128k',
      '-movflags', '+faststart',
      '-pix_fmt', 'yuv420p',
      outputPath
    ];

    const proc = spawn(ffmpegPath, args, { windowsHide: true });

    let stderr = '';
    proc.stderr.on('data', (data) => { stderr += data.toString('utf-8'); });
    proc.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(`ffmpeg preview generation failed (code ${code}): ${stderr}`));
      } else {
        resolve({ success: true, outputPath });
      }
    });
    proc.on('error', (err) => reject(new Error(`ffmpeg spawn error: ${err.message}`)));
  });
}

module.exports = { runFFprobe, generatePreview };