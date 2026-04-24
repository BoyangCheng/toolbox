const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = 3000;
const PUBLIC = __dirname + '/public';
const DATA_DIR = __dirname + '/data';
const STATE_FILE = DATA_DIR + '/state.json';

if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });

const mime = {
  '.html': 'text/html; charset=utf-8',
  '.js':   'application/javascript',
  '.css':  'text/css',
  '.json': 'application/json',
  '.png':  'image/png',
  '.svg':  'image/svg+xml',
  '.ico':  'image/x-icon',
};

function readBody(req) {
  return new Promise((resolve, reject) => {
    let data = '';
    req.on('data', chunk => { data += chunk; if (data.length > 20*1024*1024) req.destroy(); });
    req.on('end', () => resolve(data));
    req.on('error', reject);
  });
}

const server = http.createServer(async (req, res) => {
  const urlPath = req.url.split('?')[0];

  // State API
  if (urlPath === '/api/state') {
    if (req.method === 'GET') {
      try {
        const data = fs.existsSync(STATE_FILE) ? fs.readFileSync(STATE_FILE, 'utf8') : '{}';
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(data);
      } catch (e) {
        res.writeHead(500); res.end('{"error":"read_failed"}');
      }
      return;
    }
    if (req.method === 'POST') {
      try {
        const body = await readBody(req);
        JSON.parse(body); // validate
        // atomic write: tmp + rename
        const tmp = STATE_FILE + '.tmp';
        fs.writeFileSync(tmp, body);
        fs.renameSync(tmp, STATE_FILE);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end('{"ok":true}');
      } catch (e) {
        res.writeHead(400); res.end('{"error":"bad_json"}');
      }
      return;
    }
    res.writeHead(405); res.end('Method Not Allowed'); return;
  }

  // Static files
  let p = urlPath;
  if (p === '/' || p === '/dashboard') p = '/index.html';
  let filePath = path.join(PUBLIC, p);
  if (!filePath.startsWith(PUBLIC)) { res.writeHead(403); res.end('Forbidden'); return; }
  if (!path.extname(filePath) && !fs.existsSync(filePath)) filePath = path.join(PUBLIC, 'index.html');

  fs.readFile(filePath, (err, data) => {
    if (err) { res.writeHead(404, {'Content-Type':'text/plain'}); res.end('Not found'); return; }
    const ext = path.extname(filePath);
    res.writeHead(200, {'Content-Type': mime[ext] || 'application/octet-stream'});
    res.end(data);
  });
});

server.listen(PORT, () => {
  console.log(`流程图编辑器运行于 http://localhost:${PORT}`);
  console.log(`状态文件: ${STATE_FILE}`);
});
