import { useState, useEffect, useRef } from 'react';

const API = 'http://localhost:4001/todos';

function useTodos() {
  const [todos,   setTodos]   = useState([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);

  const load = async () => {
    try {
      const res = await fetch(API);
      if (!res.ok) throw new Error(`Server error ${res.status}`);
      const json = await res.json();
      setTodos(json.data ?? []);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const add = async (text, priority = 'medium') => {
    const res  = await fetch('http://localhost:4001/todos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, priority }),
    });
    const json = await res.json();
    if (json.success) setTodos(prev => [json.data, ...prev]);
  };

  const toggle = async (id, completed) => {
    setTodos(prev => prev.map(t => t.id === id ? { ...t, completed } : t));
    await fetch(`http://localhost:4001/todos/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ completed }),
    });
  };

  const remove = async (id) => {
    setTodos(prev => prev.filter(t => t.id !== id));
    await fetch(`http://localhost:4001/todos/${id}`, { method: 'DELETE' });
  };

  const clearCompleted = async () => {
    setTodos(prev => prev.filter(t => !t.completed));
    await fetch('http://localhost:4001/todos', { method: 'DELETE' });
  };

  return { todos, loading, error, add, toggle, remove, clearCompleted, reload: load };
}

// ... (rest of the code remains the same)