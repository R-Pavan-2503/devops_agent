/**
 * Todo Backend — Express REST API
 * Port: read from process.env.PORT or package.json "port" field (4001)
 * Storage: in-memory (survives only while server is running)
 * CORS: enabled for the todo frontend port (4005) and wildcard for dev
 */
const express = require('express');
const cors    = require('cors');
const { v4: uuid } = require('uuid');

const app  = express();
const PORT = process.env.PORT || 4001;

// ── Middleware ─────────────────────────────────────────────────────
app.use(express.json());
app.use(cors({
  origin: '*',          
  methods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization'],
}));

// ... (rest of the code remains the same)