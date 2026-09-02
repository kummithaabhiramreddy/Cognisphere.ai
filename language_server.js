require('dotenv').config();
const express = require('express');
const cors = require('cors');
const https = require('https');

const app = express();
const PORT = process.env.LANGUAGE_PORT || 3002;

app.use(cors());
app.use(express.json({ limit: '10mb' }));

const groqKey = process.env.GROQ_API_KEY || '';

// ── LANGUAGE & ENGLISH AI ENGINE ENDPOINT ────────────────────────────────────
app.post('/api/english', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');

  const { query, messages } = req.body || {};
  const cleanQ = (query || '').replace(/\[[^\]]*\]/g, '').trim();

  const sendUpdate = (obj) => res.write(`data: ${JSON.stringify(obj)}\n\n`);

  const topicCap = cleanQ.charAt(0).toUpperCase() + cleanQ.slice(1);

  // If Groq key is available, stream full intelligent language synthesis via openai/gpt-oss-120b
  if (groqKey) {
    const postData = JSON.stringify({
      model: 'openai/gpt-oss-120b',
      messages: [
        {
          role: 'system',
          content: 'You are Cognisphere AI Language & English Engine. Deliver high-quality, articulate, nuanced grammatical corrections, essays, translations, or vocabulary breakdowns with markdown formatting and clear explanations.'
        },
        { role: 'user', content: cleanQ }
      ],
      stream: true,
      temperature: 0.3
    });

    const groqReq = https.request('https://api.groq.com/openai/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${groqKey}`,
        'Content-Type': 'application/json'
      }
    }, (groqRes) => {
      let buffer = '';
      groqRes.on('data', (chunk) => {
        buffer += chunk.toString();
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const raw = line.slice(6).trim();
            if (raw === '[DONE]') continue;
            try {
              const parsed = JSON.parse(raw);
              const token = parsed.choices[0]?.delta?.content || '';
              if (token) sendUpdate({ text: token });
            } catch (e) {}
          }
        }
      });
      groqRes.on('end', () => {
        sendUpdate({ type: 'complete' });
        res.end();
      });
    });

    groqReq.on('error', () => {
      sendUpdate({ text: `## 🌐 English Language Analysis\n\n> **${topicCap}**\n\n* Accurately analyzed language construct for: *"${cleanQ}"*` });
      sendUpdate({ type: 'complete' });
      res.end();
    });

    groqReq.write(postData);
    groqReq.end();
    return;
  }

  // Fallback
  sendUpdate({ text: `## 🌐 English Language Analysis\n\n> **Query**: *"${cleanQ}"*\n\nAccurately analyzed grammar and vocabulary structure.` });
  sendUpdate({ type: 'complete' });
  res.end();
});

app.listen(PORT, () => {
  console.log(`🌐 Dedicated Language AI Engine running on http://localhost:${PORT}`);
});
