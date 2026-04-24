import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react';
import { App } from './App';
import { login } from './api';

jest.mock('./api');

describe('App', () => {
  it('should render the login form', () => {
    const { getByPlaceholderText } = render(<App />);
    expect(getByPlaceholderText('user')).toBeInTheDocument();
    expect(getByPlaceholderText('pass')).toBeInTheDocument();
  });

  it('should call the login function when the form is submitted', async () => {
    const { getByPlaceholderText, getByText } = render(<App />);
    const usernameInput = getByPlaceholderText('user');
    const passwordInput = getByPlaceholderText('pass');
    const loginButton = getByText('Login');

    fireEvent.change(usernameInput, { target: { value: 'test' } });
    fireEvent.change(passwordInput, { target: { value: 'test' } });
    fireEvent.click(loginButton);

    await waitFor(() => expect(login).toHaveBeenCalledTimes(1));
  });

  it('should display an error message when the login fails', async () => {
    const { getByPlaceholderText, getByText } = render(<App />);
    const usernameInput = getByPlaceholderText('user');
    const passwordInput = getByPlaceholderText('pass');
    const loginButton = getByText('Login');

    fireEvent.change(usernameInput, { target: { value: 'test' } });
    fireEvent.change(passwordInput, { target: { value: 'test' } });
    fireEvent.click(loginButton);

    login.mockRejectedValue(new Error('Error code: 401, Error message: Invalid credentials'));

    await waitFor(() => expect(getByText('Error code: 401, Error message: Invalid credentials')).toBeInTheDocument());
  });

  it('should display the login response when the login is successful', async () => {
    const { getByPlaceholderText, getByText } = render(<App />);
    const usernameInput = getByPlaceholderText('user');
    const passwordInput = getByPlaceholderText('pass');
    const loginButton = getByText('Login');

    fireEvent.change(usernameInput, { target: { value: 'test' } });
    fireEvent.change(passwordInput, { target: { value: 'test' } });
    fireEvent.click(loginButton);

    login.mockResolvedValue({
      id: 1,
      status: 'success',
      created_at: '2022-01-01T00:00:00.000Z',
      username: 'test',
    });

    await waitFor(() => expect(getByText('Welcome test')).toBeInTheDocument());
    await waitFor(() => expect(getByText('ID: 1')).toBeInTheDocument());
    await waitFor(() => expect(getByText('Status: success')).toBeInTheDocument());
    await waitFor(() => expect(getByText('Created At: 2022-01-01T00:00:00.000Z')).toBeInTheDocument());
  });

  it('should render the login form with initial values', () => {
    const { getByPlaceholderText } = render(<App />);
    const usernameInput = getByPlaceholderText('user');
    const passwordInput = getByPlaceholderText('pass');

    expect(usernameInput.value).toBe('');
    expect(passwordInput.value).toBe('');
  });

  it('should handle error code in error response', async () => {
    const { getByPlaceholderText, getByText } = render(<App />);
    const usernameInput = getByPlaceholderText('user');
    const passwordInput = getByPlaceholderText('pass');
    const loginButton = getByText('Login');

    fireEvent.change(usernameInput, { target: { value: 'test' } });
    fireEvent.change(passwordInput, { target: { value: 'test' } });
    fireEvent.click(loginButton);

    login.mockRejectedValue(new Error('Error code: 401, Error message: Invalid credentials'));

    await waitFor(() => expect(getByText('Error code: 401, Error message: Invalid credentials')).toBeInTheDocument());
  });
});