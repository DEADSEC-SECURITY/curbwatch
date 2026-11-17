const http = require('http');

function ticket(number, plate) {
  return {
    ticket_number: number, plate_number: plate, tstatusid: 19,
    issue_date: { $date: { $numberLong: '1730730600000' } },
    location: { locationid: 39, description: 'WAVERLY AVE' },
    balance: { $numberDecimal: '0.00' },
    violation: { amount: { $numberDecimal: '25.00' }, type: { display_text: 'Parking violation' } },
    surcharges: [],
  };
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  const send = (type, data, status = 200) => {
    res.writeHead(status, { 'Content-Type': type });
    res.end(typeof data === 'string' ? data : JSON.stringify(data));
  };
  if (req.method === 'GET' && url.pathname.replace(/\/$/, '') === '/tickets') {
    res.setHeader('Set-Cookie', ['AW9_CSRF=simulation-token; Path=/', 'AW9_SESSIONID=simulation-session; Path=/']);
    return send('text/html', '<html>Ticket search simulation</html>');
  }
  if (url.pathname !== '/api/tickets/index.php') return send('application/json', { error: 'Unmodeled endpoint' }, 501);
  if (req.headers['x-csrf-token'] !== 'simulation-token' || !req.headers.cookie?.includes('AW9_SESSIONID=')) {
    return send('application/json', { error: 'Session token or cookie missing' }, 403);
  }
  if (req.method === 'GET' && url.searchParams.get('cmd') === 'get_ticket_detail') {
    const detail = ticket('SIM003', 'SINGLE123');
    detail.violations = [detail.violation];
    delete detail.violation;
    return send('application/json', { ticket: detail });
  }
  if (req.method === 'POST' && url.searchParams.get('cmd') === 'search_tickets') {
    let body;
    if (req.body !== undefined) {
      body = typeof req.body === 'string' ? req.body : Buffer.isBuffer(req.body) ? req.body.toString() : JSON.stringify(req.body);
    } else {
      const chunks = [];
      for await (const chunk of req) chunks.push(chunk);
      body = Buffer.concat(chunks).toString();
    }
    if (!req.headers['content-type']?.includes('multipart/form-data') || !body.includes('ticket_search_form')) {
      return send('application/json', { error: 'Expected multipart search form' }, 400);
    }
    if (body.includes('JSONERR1')) return send('application/json', { type: 'error', message: 'No tickets found because the database is unavailable' });
    if (body.includes('MULTI123')) return send('application/json', { tickets: [ticket('SIM001', 'MULTI123'), ticket('SIM002', 'MULTI123')] });
    if (body.includes('SINGLE123')) return send('text/javascript', 'redirect("https:\\/\\/mvb.syr.gov\\/tickets\\/index.php?cmd=detail&ticketid=123");');
    if (body.includes('EMPTY123')) return send('text/javascript', '$("#no_tickets_found").modal();');
    if (body.includes('ERROR123')) return send('text/html', '<html>Temporarily unavailable</html>', 500);
    return send('text/html', '<html>Unexpected upstream page</html>');
  }
  send('application/json', { error: 'Unmodeled operation' }, 501);
});
server.listen(Number(process.env.PORT || 4510), '127.0.0.1', () => {
  console.log(JSON.stringify({port:server.address().port}));
});
