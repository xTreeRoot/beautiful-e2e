import { Tag } from 'antd';
import { Clock3 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

type ElapsedTimeTagProps = {
  startedAt: number | null;
  finishedAt?: number | null;
  running?: boolean;
  label?: string;
};

export function ElapsedTimeTag({
  startedAt,
  finishedAt = null,
  running = false,
  label = '耗时'
}: ElapsedTimeTagProps) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!running || !startedAt || finishedAt) return;
    const intervalId = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(intervalId);
  }, [finishedAt, running, startedAt]);

  const elapsedText = useMemo(() => {
    if (!startedAt) return '0:00';
    return formatElapsedTime(Math.max(0, (finishedAt ?? now) - startedAt));
  }, [finishedAt, now, startedAt]);

  if (!startedAt) return null;

  return (
    <Tag className="elapsed-time-tag" icon={<Clock3 size={13} aria-hidden="true" />}>
      {label} {elapsedText}
    </Tag>
  );
}

function formatElapsedTime(milliseconds: number): string {
  const totalSeconds = Math.floor(milliseconds / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}:${padTime(minutes)}:${padTime(seconds)}`;
  }
  return `${minutes}:${padTime(seconds)}`;
}

function padTime(value: number): string {
  return value.toString().padStart(2, '0');
}
