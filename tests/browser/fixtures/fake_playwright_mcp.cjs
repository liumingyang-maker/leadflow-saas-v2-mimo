#!/usr/bin/env node

const readline = require('node:readline');

const receivedCalls = [];
const tools = [
  'browser_navigate',
  'browser_snapshot',
  'browser_click',
  'browser_take_screenshot',
  'browser_close',
  'browser_evaluate',
].map((name) => ({ name, inputSchema: { type: 'object' } }));

function respond(id, result) {
  process.stdout.write(`${JSON.stringify({ jsonrpc: '2.0', id, result })}\n`);
}

const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
input.on('line', (line) => {
  const request = JSON.parse(line);
  if (request.method === 'initialize') {
    respond(request.id, { protocolVersion: '2025-03-26', capabilities: {} });
    return;
  }
  if (request.method === 'tools/list') {
    respond(request.id, { tools });
    return;
  }
  if (request.method === 'tools/call') {
    receivedCalls.push({
      name: request.params.name,
      arguments: request.params.arguments,
    });
    respond(request.id, {
      content: [
        {
          type: 'text',
          text: JSON.stringify({ receivedCalls }),
        },
      ],
    });
  }
});
