const express = require('express');
const cors = require('cors');

const app = express();
const PORT = process.env.IMAGE_PORT || 3003;

app.use(cors());
app.use(express.json({ limit: '10mb' }));

// ── VISUAL & IMAGE AI ENGINE ENDPOINT ────────────────────────────────────────
app.post('/api/images', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');

  const { query, messages } = req.body || {};
  const cleanQ = (query || '')
    .replace(/\[[^\]]*\]/g, '')
    .replace(/\b(image|images|photo|photos|picture|pictures|pic|pics|show me|look like|wallpapers|wallpaper|gallery)\b/gi, '')
    .trim() || 'Visual Topic';

  const sendUpdate = (obj) => res.write(`data: ${JSON.stringify(obj)}\n\n`);

  const seeds = [108, 209, 310, 411];
  const styles = ['hd realistic photo', 'cinematic detailed photo', '4k professional visual', 'vibrant clear view'];
  const encSub = encodeURIComponent(cleanQ);

  const images = seeds.map((seed, idx) => {
    const promptStr = encodeURIComponent(`${cleanQ} ${styles[idx]}`);
    return {
      src: `https://image.pollinations.ai/prompt/${promptStr}?width=800&height=600&nologo=true&seed=${seed}`,
      alt: `${cleanQ} - Visual ${idx + 1}`,
      link: `https://image.pollinations.ai/prompt/${promptStr}`
    };
  });

  let imgMarkdown = `### 🖼️ Visual Gallery — ${cleanQ.charAt(0).toUpperCase() + cleanQ.slice(1)}\n\n`;
  images.forEach(img => {
    imgMarkdown += `![${img.alt}](${img.src})\n\n`;
  });
  imgMarkdown += `> 📐 **Engine:** Dedicated Visual Engine (Port 3003) | 🤖 **Model:** Pollinations Neural Diffusion\n\n`;

  sendUpdate({ text: imgMarkdown, images });
  sendUpdate({ type: 'complete' });
  return res.end();
});

app.listen(PORT, () => {
  console.log(`🖼️ Dedicated Visual AI Engine running on http://localhost:${PORT}`);
});
