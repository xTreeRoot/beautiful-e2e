import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Button, Modal, Space, Typography } from 'antd';
import { AlertCircle, CheckCircle2, LoaderCircle } from 'lucide-react';

import type { GenerateProgressPhase } from '../../types/workbench';
import { ElapsedTimeTag } from './ElapsedTimeTag';

const { Text, Title } = Typography;

type StreamProgressModalProps = {
  open: boolean;
  runId: number;
  phase: GenerateProgressPhase;
  lines: string[];
  startedAt: number | null;
  finishedAt: number | null;
  title: string;
  titleIcon: ReactNode;
  runningTitle: string;
  completeTitle: string;
  errorTitle: string;
  runningDescription: string;
  completeDescription: string;
  errorDescription: string;
  runningButtonLabel: string;
  emptyLine: string;
  className?: string;
  autoConfirmSeconds?: number;
  onConfirm: () => void;
};

export function StreamProgressModal({
  open,
  runId,
  phase,
  lines,
  startedAt,
  finishedAt,
  title,
  titleIcon,
  runningTitle,
  completeTitle,
  errorTitle,
  runningDescription,
  completeDescription,
  errorDescription,
  runningButtonLabel,
  emptyLine,
  className = 'generate-progress-modal',
  autoConfirmSeconds = 5,
  onConfirm
}: StreamProgressModalProps) {
  const [secondsLeft, setSecondsLeft] = useState(autoConfirmSeconds);
  const consoleRef = useRef<HTMLDivElement | null>(null);
  const confirmedRef = useRef(false);

  const displayLines = lines.length > 0 ? lines : [emptyLine];
  const canConfirm = phase === 'complete' || phase === 'error';
  const isComplete = phase === 'complete';
  const isError = phase === 'error';

  useEffect(() => {
    if (!open) return;
    confirmedRef.current = false;
    setSecondsLeft(autoConfirmSeconds);
  }, [autoConfirmSeconds, open, runId]);

  useEffect(() => {
    if (!open) return;
    const consoleElement = consoleRef.current;
    if (!consoleElement) return;

    // SSE 增量会高频追加，等浏览器完成当前帧布局后再贴到底部。
    const frameId = window.requestAnimationFrame(() => {
      consoleElement.scrollTop = consoleElement.scrollHeight;
    });

    return () => window.cancelAnimationFrame(frameId);
  }, [open, lines]);

  useEffect(() => {
    if (!open || !isComplete) return;
    setSecondsLeft(autoConfirmSeconds);
    const intervalId = window.setInterval(() => {
      setSecondsLeft((current) => {
        if (current <= 1) {
          window.clearInterval(intervalId);
          if (!confirmedRef.current) {
            confirmedRef.current = true;
            onConfirm();
          }
          return 0;
        }
        return current - 1;
      });
    }, 1000);
    return () => window.clearInterval(intervalId);
  }, [autoConfirmSeconds, isComplete, onConfirm, open, runId]);

  const handleConfirm = () => {
    confirmedRef.current = true;
    onConfirm();
  };

  return (
    <Modal
      centered
      width={640}
      open={open}
      className={className}
      closable={canConfirm}
      maskClosable={canConfirm}
      keyboard={canConfirm}
      onCancel={canConfirm ? handleConfirm : undefined}
      footer={
        <Button type="primary" disabled={!canConfirm} onClick={handleConfirm}>
          {isComplete
            ? `确定 (${secondsLeft}s)`
            : isError
              ? '我知道了'
              : runningButtonLabel}
        </Button>
      }
      title={
        <Space size={10} className="generate-progress-title">
          {isComplete ? (
            <CheckCircle2 size={18} aria-hidden="true" />
          ) : isError ? (
            <AlertCircle size={18} aria-hidden="true" />
          ) : (
            titleIcon
          )}
          <span>{title}</span>
        </Space>
      }
    >
      <div className="generate-progress-body">
        <div className={`generate-progress-icon ${phase}`}>
          {phase === 'running' ? (
            <LoaderCircle size={26} aria-hidden="true" />
          ) : isError ? (
            <AlertCircle size={26} aria-hidden="true" />
          ) : (
            <CheckCircle2 size={26} aria-hidden="true" />
          )}
        </div>
        <div className="generate-progress-copy">
          <Space size={8} wrap>
            <Title level={4}>{isError ? errorTitle : isComplete ? completeTitle : runningTitle}</Title>
            <ElapsedTimeTag startedAt={startedAt} finishedAt={finishedAt} running={phase === 'running'} />
          </Space>
          <Text type="secondary">
            {isError ? errorDescription : isComplete ? completeDescription : runningDescription}
          </Text>
        </div>
      </div>

      <div ref={consoleRef} className="generate-progress-console" aria-live="polite">
        {displayLines.map((line, index) => (
          <div key={`${runId}-${index}`} className="generate-progress-line">
            <span className="generate-progress-prefix">{index + 1}</span>
            <span>{line}</span>
            {index === displayLines.length - 1 && phase === 'running' ? (
              <span className="typing-cursor" />
            ) : null}
          </div>
        ))}
      </div>
    </Modal>
  );
}
