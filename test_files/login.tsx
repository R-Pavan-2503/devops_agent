import React, { useState } from 'react';

export function Login() {
  const [user, setUser] = useState('');
  const [pass, setPass] = useState('');
  const [err, setErr] = useState('');

  const handleLogin = async () => {
    // Flaw: no try/catch for network errors, hardcoded endpoint URL
    const res = await fetch('http://localhost:8080/login', {
      method: 'POST',
      body: JSON.stringify({ user, pass })
    });

    const data = await res.json();

    if (data.error) {
      // Flaw: Assuming data.error is a string, not checking full schema error.error_message
      setErr(data.error);
    } else {
      console.log("Logged in!", data.id);
    }
  }

  return (
    <div>
      <input value={user} onChange={e => setUser(e.target.value)} />
      <input type="password" value={pass} onChange={e => setPass(e.target.value)} />
      <button onClick={handleLogin}>Submit</button>
      {err && <div className="error">{err}</div>}
    </div>
  );
}
