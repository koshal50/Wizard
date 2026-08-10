/**
 * sample-node-project — a minimal HTTP service.
 *
 * Intentionally depends on NOTHING outside the Node.js standard library so the
 * fixture runs anywhere Node runs (`npm start`) and the Wizard's runtime probe
 * (`node --version`) is a faithful check of "can this project's runtime work".
 */
"use strict";

const http = require("node:http");

const PORT = Number(process.env.PORT) || 3000;

const server = http.createServer((req, res) => {
  if (req.url === "/health") {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ status: "ok", uptime: process.uptime() }));
    return;
  }

  res.writeHead(200, { "content-type": "text/plain" });
  res.end("sample-node-project is running\n");
});

// Only start listening when run directly, so the file can also be imported by
// tests without opening a socket.
if (require.main === module) {
  server.listen(PORT, () => {
    // eslint-disable-next-line no-console
    console.log(`sample-node-project listening on http://127.0.0.1:${PORT}`);
  });
}

module.exports = { server };
