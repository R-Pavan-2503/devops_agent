import { useState } from 'react';

const API = 'http://localhost:4011/submit';

export default function App() {
  const [formData, setFormData] = useState({
    fullName: '',
    email: '',
    subject: '',
    message: '',
  });

  const [status, setStatus] = useState('idle'); 
  const [errors, setErrors] = useState({});
  const [feedback, setFeedback] = useState(null);

  const validate = () => {
    const newErrors = {};
    if (!formData.fullName.trim() || formData.fullName.trim().length < 2) {
      newErrors.fullName = 'Full name must be at least 2 characters.';
    }
    if (!formData.email.trim() || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      newErrors.email = 'A valid email address is required.';
    }
    if (!formData.subject.trim() || formData.subject.trim().length < 3) {
      newErrors.subject = 'Subject must be at least 3 characters.';
    }
    if (!formData.message.trim() || formData.message.trim().length < 10) {
      newErrors.message = 'Message must be at least 10 characters.';
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
    // Clear error when typing
    if (errors[name]) {
      setErrors(prev => ({ ...prev, [name]: null }));
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validate()) return;

    setStatus('loading');
    setFeedback(null);

    try {
      const res = await fetch(API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      });

      const json = await res.json();

      if (res.ok && json.success) {
        setStatus('success');
        setFeedback(json.message || 'Form submitted successfully!');
        setFormData({ fullName: '', email: '', subject: '', message: '' });
        setErrors({});
      } else {
        setStatus('error');
        setFeedback('Validation failed or server error.');
        if (json.errors) setErrors(json.errors);
      }
    } catch (err) {
      setStatus('error');
      setFeedback(`Server error: ${err.message}. Is the backend running?`);
    }
  };

  return (
    // ... (rest of the code remains the same)
  );
}