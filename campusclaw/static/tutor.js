// Decode complete SSE frames without assuming a network chunk is a frame.
async function consumeSSE(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8', {fatal: true});
  let buffer = '', terminal = false;
  function drain(final) {
    let match;
    while ((match = /\r?\n\r?\n/.exec(buffer))) {
      const frame = buffer.slice(0, match.index);
      buffer = buffer.slice(match.index + match[0].length);
      let event = 'message', data = [];
      for (const line of frame.split(/\r?\n/)) {
        if (line.startsWith('event:')) event = line.slice(6).trim();
        if (line.startsWith('data:')) data.push(line.slice(5).trimStart());
      }
      if (data.length) {
        if (terminal) throw new Error('结束事件后出现额外数据');
        onEvent(event, JSON.parse(data.join('\n')));
        if (event === 'done' || event === 'error') terminal = true;
      }
    }
    if (final && buffer.trim()) throw new Error('流式数据帧未完整结束');
  }
  try {
    while (true) {
      const {value, done} = await reader.read();
      buffer += done ? decoder.decode() : decoder.decode(value, {stream: true});
      drain(done);
      if (done) break;
    }
    if (!terminal) throw new Error('连接中断，回答未完成');
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

if (typeof module !== 'undefined') module.exports = {consumeSSE};
