/**
 * Todo Backend — Express REST API
 * Port: read from process.env.PORT or package.json "port" field (4001)
 * Storage: in-memory (survives only while server is running)
 * CORS: enabled for the todo frontend port (4005) and wildcard for dev
 */
const express = require('express');
const cors = require('cors');
const { v4: uuid } = require('uuid');

const app = express();
const PORT = process.env.PORT || 4001;

// ── Middleware ─────────────────────────────────────────────────────
app.use(express.json());
app.use(cors({
  origin: '*',          // Allow all origins in dev; tighten in production
  methods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization'],
}));

// ── In-Memory Store ────────────────────────────────────────────────
let todos = [
  { id: uuid(), text: 'Try adding a new task ',   completed: false, priority: 'medium', createdAt: new Date().toISOString() },
  { id: uuid(), text: 'Mark a task as complete ',  completed: false, priority: 'high',   createdAt: new Date().toISOString() },
  { id: uuid(), text: 'Delete a finished task ',  completed: true,  priority: 'low',    createdAt: new Date().toISOString() },
];

// ── Routes ─────────────────────────────────────────────────────────
/** GET /todos — return all todos */
app.get('/todos', (req, res) => {
  res.json({ success: true, data: todos, count: todos.length });
});

/** POST /todos — create a new todo */
app.post('/todos', (req, res) => {
  const { text, priority } = req.body;
  if (!text || typeof text !== 'string' || !text.trim()) {
    return res.status(400).json({ success: false, error: 'text is required' });
  }

  const validPriorities = ['low', 'medium', 'high'];
  const todoPriority = validPriorities.includes(priority) ? priority : 'medium';

  const todo = {
    id: uuid(),
    text: text.trim(),
    completed: false,
    priority: todoPriority,
    createdAt: new Date().toISOString(),
  };
  todos.unshift(todo);
  res.status(201).json({ success: true, data: todo });
});

/** PATCH /todos/:id — toggle completed or update text */
app.patch('/todos/:id', (req, res) => {
  const todo = todos.find(t => t.id === req.params.id);
  if (!todo) return res.status(404).json({ success: false, error: 'Not found' });

  const validPriorities = ['low', 'medium', 'high'];

  if (typeof req.body.completed === 'boolean') todo.completed = req.body.completed;
  if (typeof req.body.text === 'string' && req.body.text.trim()) todo.text = req.body.text.trim();
  if (validPriorities.includes(req.body.priority)) todo.priority = req.body.priority;

  res.json({ success: true, data: todo });
});

/** DELETE /todos/:id — remove a todo */
app.delete('/todos/:id', (req, res) => {
  const before = todos.length;
  todos = todos.filter(t => t.id !== req.params.id);
  if (todos.length === before) return res.status(404).json({ success: false, error: 'Not found' });
  res.json({ success: true, message: 'Deleted' });
});

/** DELETE /todos — clear all completed */
app.delete('/todos', (req, res) => {
  const removed = todos.filter(t => t.completed).length;
  todos = todos.filter(t => !t.completed);
  res.json({ success: true, message: `Cleared ${removed} completed todo(s)` });
});

/** Health check */
app.get('/health', (req, res) => res.json({ status: 'ok', port: PORT, app: 'todo-backend' }));

// ── Start ──────────────────────────────────────────────────────────
app.listen(PORT, () => {
  console.log(`\n  Todo Backend running at http://localhost:${PORT}`);
  console.log(`   GET    /todos`);
  console.log(`   POST   /todos`);
  console.log(`   PATCH  /todos/:id`);
  console.log(`   DELETE /todos/:id\n`);
});