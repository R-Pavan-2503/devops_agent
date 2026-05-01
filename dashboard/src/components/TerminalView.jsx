import { useState, useEffect, useRef } from 'react';
import { Terminal as TerminalIcon, Circle, Play, RefreshCw } from 'lucide-react';

const TerminalView = ({ prId }) => {
  const [logs, setLogs] = useState([]);
  const [status, setStatus] = useState('connecting');
  const [rateLimits, setRateLimits] = useState(null);
  const [usage, setUsage] = useState(null);
  const bottomRef = useRef(null);
  const containerRef = useRef(null);

  useEffect(() => {
    let active = true;

    const fetchMonitorData = async () => {
      try {
        const [rateRes, usageRes] = await Promise.all([
          fetch('http://localhost:8000/api/settings/rate-limits'),
          fetch('http://localhost:8000/api/settings/usage'),
        ]);
        if (!active) return;
        if (rateRes.ok) {
          const rateData = await rateRes.json();
          setRateLimits(rateData);
        }
        if (usageRes.ok) {
          const usageData = await usageRes.json();
          setUsage(usageData);
        }
      } catch {
        if (active) {
          setRateLimits({
            status: 'unavailable',
            message: 'Unable to reach rate-limit endpoint.',
            limit_tokens: 0,
            remaining_tokens: 0,
            used_tokens_window: 0,
            reset_tokens: '',
            limit_requests: 0,
            remaining_requests: 0,
            used_requests_window: 0,
            reset_requests: '',
          });
        }
      }
    };

    fetchMonitorData();
    const interval = setInterval(fetchMonitorData, 3000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    if (!prId) return;

    const eventSource = new EventSource(`http://localhost:8000/api/prs/${prId}/logs/stream`);

    eventSource.onmessage = (event) => {
      setLogs((prev) => [...prev, event.data]);
      setStatus('connected');
    };

    eventSource.onerror = (error) => {
      console.error('SSE Error:', error);
      setStatus('error');
    };

    return () => {
      eventSource.close();
    };
  }, [prId]);

  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  const formatLogLine = (line) => {
    if (line.includes('[worker] [OK]') || line.includes('âœ…')) {
      return <span className="text-success">{line}</span>;
    }
    if (line.includes('Error') || line.includes('Failed') || line.includes('Exception')) {
      return <span className="text-error font-semibold">{line}</span>;
    }
    if (line.includes('Warning') || line.includes('âš ï¸')) {
      return <span className="text-yellow-400">{line}</span>;
    }
    if (line.includes('ðŸš€') || line.includes('ðŸ“¦')) {
      return <span className="text-primary font-medium">{line}</span>;
    }
    if (line.includes('[frontend_agent]') || line.includes('[backend_agent]') || line.includes('[security_agent]')) {
      return <span className="text-secondary">{line}</span>;
    }
    return <span className="text-gray-300">{line}</span>;
  };

  if (!prId) {
    return (
      <div className="h-full bg-background p-6 flex flex-col gap-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div className="rounded-lg border border-slate-700 bg-[#111827] p-4">
            <div className="text-xs uppercase tracking-wide text-gray-400">Window Tokens Used</div>
            <div className="mt-1 text-xl font-semibold">{rateLimits?.used_tokens_window ?? 0}</div>
            <div className="text-xs text-gray-500">limit: {rateLimits?.limit_tokens || '-'}</div>
          </div>
          <div className="rounded-lg border border-slate-700 bg-[#111827] p-4">
            <div className="text-xs uppercase tracking-wide text-gray-400">Window Requests Used</div>
            <div className="mt-1 text-xl font-semibold">{rateLimits?.used_requests_window ?? 0}</div>
            <div className="text-xs text-gray-500">limit: {rateLimits?.limit_requests || '-'}</div>
          </div>
          <div className="rounded-lg border border-slate-700 bg-[#111827] p-4">
            <div className="text-xs uppercase tracking-wide text-gray-400">Rolling 60s Tokens</div>
            <div className="mt-1 text-xl font-semibold">{usage?.rolling?.tokens_last_window ?? 0}</div>
            <div className="text-xs text-gray-500">real-time flow</div>
          </div>
          <div className="rounded-lg border border-slate-700 bg-[#111827] p-4">
            <div className="text-xs uppercase tracking-wide text-gray-400">Session Total Tokens</div>
            <div className="mt-1 text-xl font-semibold">{usage?.total?.tokens_used ?? 0}</div>
            <div className="text-xs text-gray-500">since page load</div>
          </div>
        </div>

        <div className="flex-1 flex items-center justify-center text-gray-500 flex-col gap-4">
          <TerminalIcon className="w-16 h-16 opacity-20" />
          <p className="text-lg">Select a Pull Request to view logs</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-background p-6">
      <div className="mb-4 grid grid-cols-1 md:grid-cols-5 gap-3 text-sm">
        <div className="rounded-lg border border-slate-700 bg-[#111827] p-3">
          <div className="text-xs text-gray-400 uppercase tracking-wide">Rate Token Used</div>
          <div className="font-semibold mt-1">{rateLimits?.used_tokens_window ?? 0} / {rateLimits?.limit_tokens || '-'}</div>
        </div>
        <div className="rounded-lg border border-slate-700 bg-[#111827] p-3">
          <div className="text-xs text-gray-400 uppercase tracking-wide">Rate Request Used</div>
          <div className="font-semibold mt-1">{rateLimits?.used_requests_window ?? 0} / {rateLimits?.limit_requests || '-'}</div>
        </div>
        <div className="rounded-lg border border-slate-700 bg-[#111827] p-3">
          <div className="text-xs text-gray-400 uppercase tracking-wide">Remaining Tokens</div>
          <div className="font-semibold mt-1">{rateLimits?.remaining_tokens ?? 0}</div>
        </div>
        <div className="rounded-lg border border-slate-700 bg-[#111827] p-3">
          <div className="text-xs text-gray-400 uppercase tracking-wide">Rolling 60s</div>
          <div className="font-semibold mt-1">{usage?.rolling?.tokens_last_window ?? 0} tok / {usage?.rolling?.requests_last_window ?? 0} req</div>
        </div>
        <div className="rounded-lg border border-slate-700 bg-[#111827] p-3">
          <div className="text-xs text-gray-400 uppercase tracking-wide">Session Total</div>
          <div className="font-semibold mt-1">{usage?.total?.tokens_used ?? 0} tokens</div>
        </div>
      </div>
      {rateLimits?.status !== 'ok' && (
        <div className="mb-4 text-xs text-yellow-400 border border-yellow-500/30 bg-yellow-500/10 rounded-md px-3 py-2">
          {rateLimits?.message || 'Rate-limit data unavailable.'}
        </div>
      )}

      <div className="flex-1 border border-slate-700 rounded-lg overflow-hidden flex flex-col bg-[#111827]">
        <div className="bg-[#0f172a] px-4 py-3 flex items-center justify-between border-b border-slate-700 select-none">
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
