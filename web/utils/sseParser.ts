/**
 * SSE 解析工具模块
 * 提供 SSE 帧解析、事件提取、JSON 解析等功能
 */

export type ParsedSseFrames = {
  frames: string[];
  buffer: string;
};

/**
 * 解析 SSE 数据帧
 * @param chunk 新接收的数据块
 * @param buffer 之前未完成的缓冲区
 * @returns 解析后的帧列表和剩余缓冲区
 */
export const parseSseFrames = (chunk: string, buffer: string): ParsedSseFrames => {
  const nextBuffer = buffer + chunk;
  const parts = nextBuffer.split('\n\n');
  return {
    frames: parts.slice(0, -1),
    buffer: parts[parts.length - 1] || '',
  };
};

/**
 * 从 SSE 帧中提取 data 字段内容
 * @param frame SSE 帧文本
 * @returns data 字段内容，若无 data 字段则返回 null
 */
export const extractSseData = (frame: string): string | null => {
  const lines = frame.split('\n');
  for (const line of lines) {
    if (line.startsWith('data: ')) {
      return line.slice('data: '.length);
    }
    if (line === 'data:') {
      return '';
    }
  }
  return null;
};

/**
 * 批量解析 SSE 帧中的 JSON 数据
 * @param frames SSE 帧列表
 * @returns 解析结果列表，包含原始帧和解析后的 JSON 对象（或解析错误）
 */
export const parseSseFramesToJson = (
  frames: string[],
): Array<{ frame: string; data: string | null; json: unknown | null; error: Error | null }> => {
  return frames.map((frame) => {
    const data = extractSseData(frame);
    if (data === null) {
      return { frame, data: null, json: null, error: null };
    }
    try {
      const json = JSON.parse(data);
      return { frame, data, json, error: null };
    } catch (e) {
      return { frame, data, json: null, error: e instanceof Error ? e : new Error(String(e)) };
    }
  });
};

/**
 * SSE 事件处理器接口
 */
export type SseEventHandler<T = unknown> = {
  type: string;
  handler: (payload: T, context: SseEventContext) => void | Promise<void>;
};

export type SseEventContext = {
  requestId: string;
  sessionId: string | null;
  sequence: number;
  timestamp: string;
};

/**
 * SSE 事件分发器
 * 根据事件类型调用对应的处理器
 */
export class SseEventDispatcher {
  private handlers: Map<string, SseEventHandler> = new Map();

  register<T>(handler: SseEventHandler<T>): void {
    this.handlers.set(handler.type, handler as SseEventHandler);
  }

  async dispatch(type: string, payload: unknown, context: SseEventContext): Promise<boolean> {
    const handler = this.handlers.get(type);
    if (handler) {
      await handler.handler(payload, context);
      return true;
    }
    return false;
  }
}
