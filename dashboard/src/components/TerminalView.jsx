import React, { useState, useEffect, useRef } from 'react';
import { Terminal as TerminalIcon, Circle, Play, RefreshCw } from 'lucide-react';

const TerminalView = ({ prId }) => {
  const [logs, setLogs] = useState([]);
  const [status, setStatus] = useState('connecting');
  const bottomRef = useRef(null);
  const containerRef = useRef(null);

  useEffect(() => {
    if (!prId) return;

    setLogs([]);
    setStatus('connecting');

    const eventSource = new EventSource(`http://localhost:8000/api/prs/${prId}/logs/stream`);

    eventSource.onmessage = (event) => {
      setLogs((prev) => [...prev, event.data]);
      setStatus('connected');
    };

    eventSource.onerror = (error) => {
      console.error("SSE Error:", error);
      setStatus('error');
      // Do not close immediately, let it retry or stay open for tailing
    };

    return () => {
      eventSource.close();
    };
  }, [prId]);

  useEffect(() => {
    // Auto-scroll to bottom
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  // Colorize log line based on content
  const formatLogLine = (line) => {
    if (line.includes('[worker] [OK]') || line.includes('✅')) {
      return <span className="text-success">{line}</span>;
    }
    if (line.includes('Error') || line.includes('Failed') || line.includes('Exception')) {
      return <span className="text-error font-semibold">{line}</span>;
    }
    if (line.includes('Warning') || line.includes('⚠️')) {
      return <span className="text-yellow-400">{line}</span>;
    }
    if (line.includes('🚀') || line.includes('📦')) {
      return <span className="text-primary font-medium">{line}</span>;
    }
    // Agent thoughts
    if (line.includes('[frontend_agent]') || line.includes('[backend_agent]') || line.includes('[security_agent]')) {
      return <span className="text-secondary">{line}</span>;
    }
    return <span className="text-gray-300">{line}</span>;
  };

  if (!prId) {
    return (
      <div className="h-full flex items-center justify-center bg-background text-gray-500 flex-col gap-4">
        <TerminalIcon className="w-16 h-16 opacity-20" />
        <p className="text-lg">Select a Pull Request to view logs</p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-background p-6">
      <div className="flex-1 border border-border rounded-lg overflow-hidden flex flex-col shadow-2xl bg-[#0d1117]">
        {/* Terminal Header */}
        <div className="bg-[#161b22] px-4 py-3 flex items-center justify-between border-b border-border select-none">
          <div className="flex items-center gap-2">
            <div className="flex gap-1.5">
              <Circle className="w-3 h-3 text-error fill-current" />
              <Circle className="w-3 h-3 text-yellow-500 fill-current" />
              <Circle className="w-3 h-3 text-success fill-current" />
            </div>
            <div className="ml-4 flex items-center gap-2 text-xs font-mono text-gray-400">
              <TerminalIcon className="w-4 h-4" />
              <span>devops-worker ~ PR #{prId}</span>
            </div>
          </div>
          
          <div className="flex items-center gap-2 text-xs">
            {status === 'connecting' && (
              <span className="flex items-center gap-1.5 text-yellow-500 bg-yellow-500/10 px-2 py-1 rounded-full">
                <RefreshCw className="w-3 h-3 animate-spin" /> Connecting...
              </span>
            )}
            {status === 'connected' && (
              <span className="flex items-center gap-1.5 text-success bg-success/10 px-2 py-1 rounded-full">
                <div className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" /> Live
              </span>
            )}
            {status === 'error' && (
              <span className="flex items-center gap-1.5 text-gray-500 bg-gray-800 px-2 py-1 rounded-full">
                <Play className="w-3 h-3" /> Stopped
              </span>
            )}
          </div>
        </div>

        {/* Terminal Body */}
        <div 
          ref={containerRef}
          className="flex-1 overflow-y-auto p-4 font-mono text-sm leading-relaxed"
        >
          {logs.length === 0 && status === 'connected' && (
            <div className="text-gray-500 italic">Waiting for pipeline to emit logs...</div>
          )}
          
          {logs.map((line, index) => (
            <div key={index} className="whitespace-pre-wrap break-words hover:bg-white/5 px-1 rounded transition-colors">
              {formatLogLine(line)}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      </div>
    </div>
  );
};

export default TerminalView;
