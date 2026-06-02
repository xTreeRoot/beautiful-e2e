type JsonSseEvent = { type: string; message?: unknown };

type StreamJsonSseOptions<TEvent extends JsonSseEvent> = {
  onEvent?: (event: TEvent) => void;
  unsupportedMessage: string;
  errorMessage: string;
};

/**
 * 统一消费后端 `text/event-stream` JSON 帧。
 * 业务 API 只负责解释事件含义，分帧、解码和错误事件处理集中在这里。
 */
export async function streamJsonSse<TEvent extends JsonSseEvent>(
  url: string,
  init: RequestInit,
  { onEvent, unsupportedMessage, errorMessage }: StreamJsonSseOptions<TEvent>
): Promise<void> {
  const response = await fetch(url, {
    ...init,
    headers: {
      Accept: 'text/event-stream',
      ...(init.headers ?? {})
    }
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `请求失败：${response.status}`);
  }
  if (!response.body) throw new Error(unsupportedMessage);

  const decoder = new TextDecoder();
  const reader = response.body.getReader();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    let frame = takeSseFrame(buffer);
    while (frame) {
      buffer = frame.rest;
      handleFrame(frame.value, onEvent, errorMessage);
      frame = takeSseFrame(buffer);
    }
    if (done) break;
  }

  handleFrame(buffer, onEvent, errorMessage);
}

function handleFrame<TEvent extends JsonSseEvent>(
  frame: string,
  onEvent: ((event: TEvent) => void) | undefined,
  errorMessage: string
) {
  const event = parseSseFrame<TEvent>(frame);
  if (!event) return;
  onEvent?.(event);
  if (event.type === 'error') {
    const message = typeof event.message === 'string' ? event.message : errorMessage;
    throw new Error(message || errorMessage);
  }
}

function takeSseFrame(buffer: string): { value: string; rest: string } | null {
  const match = buffer.match(/\r?\n\r?\n/);
  if (!match || match.index === undefined) return null;
  return {
    value: buffer.slice(0, match.index),
    rest: buffer.slice(match.index + match[0].length)
  };
}

function parseSseFrame<TEvent extends JsonSseEvent>(frame: string): TEvent | null {
  if (!frame.trim()) return null;
  let type = 'message';
  const dataLines: string[] = [];
  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith('event:')) type = line.slice('event:'.length).trim();
    if (line.startsWith('data:')) dataLines.push(line.slice('data:'.length).trimStart());
  }
  if (dataLines.length === 0) return { type } as TEvent;

  const parsed = JSON.parse(dataLines.join('\n')) as unknown;
  if (parsed && typeof parsed === 'object') {
    return { ...(parsed as Record<string, unknown>), type } as TEvent;
  }
  return { type, message: String(parsed) } as unknown as TEvent;
}
