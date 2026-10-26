const assert = require('node:assert/strict');
const {consumeSSE} = require('../campusclaw/static/tutor.js');
(async () => {
  const wire='event: meta\r\ndata: {"sources":[]}\r\n\r\nevent: delta\r\ndata: {"text":"中文新增"}\r\n\r\nevent: done\r\ndata: {"status":"completed"}\r\n\r\n';
  const bytes=new TextEncoder().encode(wire);
  const events=[];
  const response={body:new ReadableStream({start(c){for(let i=0;i<bytes.length;i++) c.enqueue(bytes.slice(i,i+1));c.close();}})};
  await consumeSSE(response,(e,d)=>events.push([e,d]));
  assert.equal(events[1][1].text,'中文新增'); assert.equal(events.at(-1)[0],'done');
  const partial={body:new ReadableStream({start(c){c.enqueue(new TextEncoder().encode('event: delta\ndata: {"text":"partial"}\n\n'));c.close();}})};
  await assert.rejects(consumeSSE(partial,()=>{}),/未完成/);
  console.log('PASS UTF-8 byte boundaries, CRLF frames, terminal detection');
})();
