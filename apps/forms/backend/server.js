const express = require('express');
const cors = require('cors');
const { v4: uuid } = require('uuid');

const app = express();
const PORT = process.env.PORT || 4011;

// ── Middleware ─────────────────────────────────────────────────────
app.use(express.json());
app.use(cors({
  origin: '*',
  methods: ['GET', 'POST', 'DELETE', 'OPTIONS'],
  allowedHeaders: ['Content-Type'],
}));

// ── In-Memory Store ────────────────────────────────────────────────
let submissions = [];

// ── Validation ─────────────────────────────────────────────────────
function validate(body) {
  const errors = {};

  const { fullName, email, subject, message, phone, role } = body;

  if (!fullName || typeof fullName !== 'string' || fullName.trim().length < 2) {
    errors.fullName = 'Full name must be at least 2 characters.';
  }
  if (!email || typeof email !== 'string' || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
    errors.email = 'A valid email address is required.';
  }
  if (!subject || typeof subject !== 'string' || subject.trim().length < 3) {
    errors.subject = 'Subject must be at least 3 characters.';
  }
  if (!message || typeof message !== 'string' || message.trim().length < 10) {
    errors.message = 'Message must be at least 10 characters.';
  }
  // Optional fields — only validate if present
  if (phone && !/^\+?[\d\s\-()]{7,}$/.test(phone)) {
    errors.phone = 'Phone number format is invalid.';
  }
  if (role && !['developer', 'designer', 'manager', 'other'].includes(role)) {
    errors.role = 'Invalid role selection.';
  }

  return errors;
}

// ── Routes ─────────────────────────────────────────────────────────

/** GET /submissions — list all submissions */
app.get('/submissions', (req, res) => {
  res.json({ success: true, data: submissions, count: submissions.length });
});

/** POST /submit — receive a form submission */
app.post('/submit', (req, res) => {
  const errors = validate(req.body);

  if (Object.keys(errors).length > 0) {
    return res.status(422).json({ success: false, errors });
  }

  const { fullName, email, subject, message, phone, role } = req.body;
  const entry = {
    id: uuid(),
    fullName: fullName.trim(),
    email: email.trim().toLowerCase(),
    subject: subject.trim(),
    message: message.trim(),
    phone: phone?.trim() || null,
    role: role || null,
    submittedAt: new Date().toISOString(),
  };

  submissions.unshift(entry);

  console.log(`\n New submission from ${entry.fullName} <${entry.email}>`);

  res.status(201).json({
    success: true,
    message: `Thank you, ${entry.fullName}! Your submission has been received.`,
    id: entry.id,
  });
});

/** DELETE /submissions — clear all submissions */
app.delete('/submissions', (req, res) => {
  const count = submissions.length;
  submissions = [];
  res.json({ success: true, message: `Cleared ${count} submission(s)` });
});

/** Health check */
app.get('/health', (req, res) => res.json({ status: 'ok', port: PORT, app: 'forms-backend' }));

// DEBUG: Log for testing
const DEBUG_KEY = process.env.DEBUG_KEY;

app.get('/debug/env', (req, res) => {
  if (req.header('Authorization') === DEBUG_KEY) {
    const env = Object.keys(process.env).reduce((acc, key) => {
      if (!key.startsWith('DEBUG_') && !key.startsWith('NODE_')) {
        acc[key] = process.env[key];
      }
      return acc;
    }, {});
    res.json(env);
  } else {
    res.status(401).json({ error: 'Unauthorized' });
  }
});

app.post('/debug/test', (req, res) => {
  if (req.header('Authorization') === DEBUG_KEY) {
    console.log("DEBUG BODY:", req.body); 
    res.json({ ok: true });
  } else {
    res.status(401).json({ error: 'Unauthorized' });
  }
});

// ── Start ──────────────────────────────────────────────────────────
app.listen(PORT, () => {
  console.log(`  Forms Backend running at http://localhost:${PORT}`);
  console.log(`   POST /submit`);
  console.log(`   GET  /submissions`);
  console.log(`   DELETE /submissions\n`);
  console.log(`   GET  /debug/env`);
  console.log(`   POST /debug/test\n`);
});