export default {
  async email(message, env, ctx) {
    const address = message.to.toLowerCase();
    if (!address.endsWith('@zhidexiu.com')) return;
    const reader = message.raw.getReader();
    const chunks = [];
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
    }
    let total = 0;
    for (const c of chunks) total += c.length;
    const merged = new Uint8Array(total);
    let offset = 0;
    for (const c of chunks) { merged.set(c, offset); offset += c.length; }
    const raw = new TextDecoder().decode(merged);
    const email = {
      id: crypto.randomUUID(),
      from: message.from || '',
      to: address,
      subject: message.headers.get('subject') || '',
      date: new Date().toISOString(),
      raw: raw.substring(0, 50000),
    };
    const key = 'inbox:' + address;
    let existing = [];
    try {
      const val = await env.MAIL_KV.get(key, 'json');
      if (Array.isArray(val)) existing = val;
    } catch (e) {}
    existing.push(email);
    if (existing.length > 20) existing = existing.slice(-20);
    await env.MAIL_KV.put(key, JSON.stringify(existing), { expirationTtl: 86400 * 7 });
  },

  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;
    const cors = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'GET, DELETE, OPTIONS', 'Access-Control-Allow-Headers': '*' };
    if (method === 'OPTIONS') return new Response(null, { headers: cors });
    if (path === '/api/health') {
      return new Response(JSON.stringify({ status: 'ok' }), { headers: { 'Content-Type': 'application/json', ...cors } });
    }
    if (path === '/api/inbox') {
      const email = url.searchParams.get('email');
      if (!email) return new Response(JSON.stringify({ error: 'missing email' }), { status: 400, headers: { 'Content-Type': 'application/json', ...cors } });
      if (method === 'DELETE') {
        await env.MAIL_KV.delete('inbox:' + email.toLowerCase());
        return new Response(JSON.stringify({ ok: true }), { headers: { 'Content-Type': 'application/json', ...cors } });
      }
      let emails = [];
      try {
        const val = await env.MAIL_KV.get('inbox:' + email.toLowerCase(), 'json');
        if (Array.isArray(val)) emails = val;
      } catch (e) {}
      return new Response(JSON.stringify({ emails: emails }), { headers: { 'Content-Type': 'application/json', ...cors } });
    }
    if (path === '/api/otp') {
      const email = (url.searchParams.get('email') || '').toLowerCase();
      if (!email) return new Response(JSON.stringify({ error: 'missing email' }), { status: 400, headers: { 'Content-Type': 'application/json', ...cors } });
      let emails = [];
      try {
        const val = await env.MAIL_KV.get('inbox:' + email, 'json');
        if (Array.isArray(val)) emails = val;
      } catch (e) {}
      for (const mail of [...emails].reverse()) {
        const body = (mail.subject + ' ' + (mail.raw || '')).toLowerCase();
        if (body.includes('openai') || body.includes('chatgpt') || body.includes('verify') || body.includes('code')) {
          const m = (mail.raw || '').match(/(?:verification|code|otp|is)[:\\s]*(\\d{6})/i);
          if (m) return new Response(JSON.stringify({ found: true, code: m[1] }), { headers: { 'Content-Type': 'application/json', ...cors } });
        }
      }
      return new Response(JSON.stringify({ found: false, count: emails.length }), { headers: { 'Content-Type': 'application/json', ...cors } });
    }
    return new Response('not found', { status: 404, headers: cors });
  }
};
