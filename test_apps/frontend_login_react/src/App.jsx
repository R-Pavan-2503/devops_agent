import React, { useState } from 'react';
import { login } from './api';
import { businessLogic } from './businessLogic';

const LoginForm = ({ handleLogin, username, password, setUsername, setPassword }) => {
  return (
    <form onSubmit={handleLogin}>
      <input placeholder="user" value={username} onChange={(e) => setUsername(e.target.value)} />
      <input type="password" placeholder="pass" value={password} onChange={(e) => setPassword(e.target.value)} />
      <button>Login</button>
    </form>
  );
};

const LoginResponse = ({ loginResponse, message }) => {
  if (loginResponse.id) {
    return (
      <p>
        ID: {loginResponse.id}
        <br />
        Status: {loginResponse.status}
        <br />
        Created At: {loginResponse.created_at}
      </p>
    );
  } else {
    return <p>{message}</p>;
  }
};

export default function App() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState('');
  const [loginResponse, setLoginResponse] = useState({});

  const handleLogin = async (e) => {
    e.preventDefault();
    try {
      const response = await login(username, password, businessLogic);
      setLoginResponse(response);
      if (response.status === 'success') {
        setMessage(`Welcome ${response.username}`);
      } else {
        setMessage(response.error_message);
      }
    } catch (err) {
      setMessage(err.message);
    }
  };

  return (
    <div>
      <LoginForm
        handleLogin={handleLogin}
        username={username}
        password={password}
        setUsername={setUsername}
        setPassword={setPassword}
      />
      <LoginResponse loginResponse={loginResponse} message={message} />
    </div>
  );
}