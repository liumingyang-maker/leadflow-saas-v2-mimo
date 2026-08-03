#!/usr/bin/env node

const { spawn } = require('node:child_process');
const readline = require('node:readline');

const separator = process.argv.indexOf('--');
const upstreamArgv = separator < 0 ? [] : process.argv.slice(separator + 1);

if (upstreamArgv.length === 0) {
  process.stderr.write('restricted Playwright MCP requires an upstream command after --\n');
  process.exit(64);
}

const toolSchemas = [
  {
    name: 'browser_navigate',
    description: 'Navigate to an approved public HTTPS URL.',
    inputSchema: {
      type: 'object',
      properties: { url: { type: 'string' } },
      required: ['url'],
      additionalProperties: false,
    },
  },
  {
    name: 'browser_snapshot',
    description: 'Capture the current page accessibility snapshot.',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
  },
  {
    name: 'browser_click',
    description: 'Follow a validated reference from the current page snapshot.',
    inputSchema: {
      type: 'object',
      properties: { target: { type: 'string' } },
      required: ['target'],
      additionalProperties: false,
    },
  },
  {
    name: 'browser_take_screenshot',
    description: 'Capture a bounded PNG evidence artifact.',
    inputSchema: {
      type: 'object',
      properties: {
        type: { type: 'string', enum: ['png'] },
        filename: { type: 'string' },
      },
      required: ['type', 'filename'],
      additionalProperties: false,
    },
  },
  {
    name: 'browser_close',
    description: 'Close the isolated browser context.',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
  },
];

function isPlainObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function hasOnlyKeys(value, keys) {
  return isPlainObject(value) && Object.keys(value).every((key) => keys.includes(key));
}

function nonEmptyString(value, maximumLength) {
  return typeof value === 'string' && value.length > 0 && value.length <= maximumLength;
}

function validateCall(params) {
  if (!hasOnlyKeys(params, ['name', 'arguments']) || typeof params.name !== 'string') {
    return null;
  }
  const args = params.arguments;
  switch (params.name) {
    case 'browser_navigate':
      if (hasOnlyKeys(args, ['url']) && nonEmptyString(args.url, 4096)) {
        return { name: params.name, arguments: { url: args.url } };
      }
      return null;
    case 'browser_snapshot':
    case 'browser_close':
      if (hasOnlyKeys(args, []) && Object.keys(args).length === 0) {
        return { name: params.name, arguments: {} };
      }
      return null;
    case 'browser_click':
      if (hasOnlyKeys(args, ['target']) && nonEmptyString(args.target, 256)) {
        return { name: params.name, arguments: { target: args.target } };
      }
      return null;
    case 'browser_take_screenshot':
      if (
        hasOnlyKeys(args, ['type', 'filename']) &&
        args.type === 'png' &&
        typeof args.filename === 'string' &&
        /^[a-f0-9]{64}\.png$/.test(args.filename)
      ) {
        return {
          name: params.name,
          arguments: { type: 'png', filename: args.filename, scale: 'css' },
        };
      }
      return null;
    default:
      return undefined;
  }
}

const upstream = spawn(upstreamArgv[0], upstreamArgv.slice(1), {
  shell: false,
  stdio: ['pipe', 'pipe', 'pipe'],
  windowsHide: true,
});
upstream.stderr.resume();

const pending = new Set();
let shuttingDown = false;

function idKey(id) {
  return JSON.stringify(id);
}

function send(payload) {
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

function response(id, result) {
  if (id !== undefined) {
    send({ jsonrpc: '2.0', id, result });
  }
}

function error(id, code) {
  if (id !== undefined) {
    send({ jsonrpc: '2.0', id, error: { code, message: 'restricted MCP request rejected' } });
  }
}

function forward(request) {
  if (request.id !== undefined) {
    pending.add(idKey(request.id));
  }
  upstream.stdin.write(`${JSON.stringify(request)}\n`);
}

function shutdown() {
  if (shuttingDown) {
    return;
  }
  shuttingDown = true;
  upstream.stdin.end();
  if (!upstream.killed) {
    upstream.kill('SIGTERM');
    setTimeout(() => {
      if (!upstream.killed) {
        upstream.kill('SIGKILL');
      }
    }, 1000).unref();
  }
}

const upstreamOutput = readline.createInterface({ input: upstream.stdout, crlfDelay: Infinity });
upstreamOutput.on('line', (line) => {
  let payload;
  try {
    payload = JSON.parse(line);
  } catch {
    return;
  }
  if (!isPlainObject(payload) || payload.id === undefined || !pending.has(idKey(payload.id))) {
    return;
  }
  pending.delete(idKey(payload.id));
  send(payload);
});

upstream.on('error', () => shutdown());
upstream.on('exit', () => {
  if (!shuttingDown && pending.size > 0) {
    for (const key of pending) {
      error(JSON.parse(key), -32000);
    }
  }
  pending.clear();
  if (!shuttingDown) {
    process.exitCode = 1;
  }
});

const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
input.on('line', (line) => {
  let request;
  try {
    request = JSON.parse(line);
  } catch {
    error(null, -32700);
    return;
  }
  if (!isPlainObject(request) || request.jsonrpc !== '2.0' || typeof request.method !== 'string') {
    error(request && request.id, -32600);
    return;
  }
  if (request.method === 'initialize') {
    if (!isPlainObject(request.params)) {
      error(request.id, -32602);
      return;
    }
    forward(request);
    return;
  }
  if (request.method === 'notifications/initialized') {
    if (request.id !== undefined || !isPlainObject(request.params)) {
      error(request.id, -32600);
      return;
    }
    forward(request);
    return;
  }
  if (request.method === 'tools/list') {
    if (!isPlainObject(request.params) || Object.keys(request.params).length !== 0) {
      error(request.id, -32602);
      return;
    }
    response(request.id, { tools: toolSchemas });
    return;
  }
  if (request.method === 'tools/call') {
    const validated = validateCall(request.params);
    if (validated === undefined) {
      error(request.id, -32601);
      return;
    }
    if (validated === null) {
      error(request.id, -32602);
      return;
    }
    forward({ jsonrpc: '2.0', id: request.id, method: 'tools/call', params: validated });
    return;
  }
  error(request.id, -32601);
});

input.on('close', shutdown);
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
