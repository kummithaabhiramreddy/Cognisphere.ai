const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '.env') });
const { Pool } = require('pg');

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: process.env.DATABASE_URL.includes('neon.tech') ? { rejectUnauthorized: false } : undefined
});

function cleanText(str) {
  if (!str || typeof str !== 'string') return str || '';
  return str
    .replace(/={5,}[\s\S]*?\[PREVIOUS CONVERSATION HISTORY & CONTEXT\]:[\s\S]*?={5,}(\nInstruction:[^\n]*)?/gi, '')
    .replace(/\[PREVIOUS CONVERSATION HISTORY & CONTEXT\]:?/gi, '')
    .replace(/\[Turn \d+ - (USER|ASSISTANT)\]:?/gi, '')
    .replace(/\[DECODED ATTACHED TEXT SENTENCES & REFERENCES\]:[\s\S]*?Focus ONLY on what the content contains\./gi, '')
    .replace(/={5,}/g, '')
    .trim();
}

async function run() {
  try {
    const res = await pool.query('SELECT id, query, response FROM search_history');
    let count = 0;
    for (let row of res.rows) {
      const q = row.query || '';
      const a = row.response || '';
      const cleanQ = cleanText(q);
      const cleanA = cleanText(a);
      if (cleanQ !== q || cleanA !== a) {
        await pool.query('UPDATE search_history SET query = $1, response = $2 WHERE id = $3', [cleanQ, cleanA, row.id]);
        count++;
      }
    }
    console.log(`Scrubbed ${count} legacy DB records cleanly.`);
  } catch(e) {
    console.error('Scrub error:', e.message);
  } finally {
    await pool.end();
  }
}
run();
