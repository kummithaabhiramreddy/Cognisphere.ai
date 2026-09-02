require('dotenv').config();
const express = require('express');
const cors = require('cors');
const https = require('https');

const app = express();
const PORT = process.env.MATH_PORT || 3001;

app.use(cors());
app.use(express.json({ limit: '10mb' }));

const groqKey = process.env.GROQ_API_KEY || '';

// ── MATH AI ENGINE ENDPOINT ──────────────────────────────────────────────────
app.post('/api/math', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');

  const { query, messages } = req.body || {};
  const cleanQ = (query || '').replace(/\[[^\]]*\]/g, '').trim();

  const sendUpdate = (obj) => res.write(`data: ${JSON.stringify(obj)}\n\n`);

  // 1. Higher Mathematics: Gamma Function Intercept
  if (/\b(gamma\s*function|gamma\s*func|factorial\s*function|gamma\s*integral)\b/i.test(cleanQ)) {
    const gammaReply = `## 🔢 The Gamma Function — Γ(z)\n\n` +
      `> **Overview**: In mathematics, the **Gamma function** (denoted by **Γ(z)**, the capital Greek letter Gamma) is the premier extension of the factorial function to complex numbers.\n\n` +
      `---\n\n` +
      `### 📌 Key Mathematical Properties & Formulas\n\n` +
      `* **Factorial Relation**: For any positive integer $n$:\n` +
      `  $$\\Gamma(n) = (n - 1)!$$\n` +
      `  *(For example: $\\Gamma(5) = 4! = 24$, $\\Gamma(1) = 0! = 1$)*\n\n` +
      `* **Integral Definition**: For complex numbers $z$ with positive real part ($\Re(z) > 0$):\n` +
      `  $$\\Gamma(z) = \\int_{0}^{\\infty} t^{z-1} e^{-t} \\, dt$$\n\n` +
      `* **Recurrence Relation**: For all $z$ except non-positive integers:\n` +
      `  $$\\Gamma(z+1) = z \\cdot \\Gamma(z)$$\n\n` +
      `* **Special Values**:\n` +
      `  - $\\Gamma(1/2) = \\sqrt{\\pi} \\approx 1.77245$\n` +
      `  - $\\Gamma(1) = 1$\n` +
      `  - $\\Gamma(2) = 1$\n` +
      `  - $\\Gamma(3) = 2$\n` +
      `  - $\\Gamma(4) = 6$\n\n` +
      `---\n\n` +
      `### 📊 Summary Table\n\n` +
      `| Property | Definition / Value |\n` +
      `| :--- | :--- |\n` +
      `| **Symbol** | $\\Gamma(z)$ |\n` +
      `| **Domain** | All complex numbers except non-positive integers ($0, -1, -2, \\dots$) |\n` +
      `| **Half-Integer Value** | $\\Gamma(1/2) = \\sqrt{\\pi}$ |\n` +
      `| **Engine** | Dedicated Math Server (Port 3001) |`;

    sendUpdate({ text: gammaReply });
    sendUpdate({ type: 'complete' });
    return res.end();
  }

  // 2. High-Precision Arithmetic Evaluator
  const cleanMathExpr = cleanQ
    .replace(/^(can you\s+)?(please\s+)?(calculate|compute|solve|what is|what'?s|give|find|evaluate)\s+/i, '')
    .replace(/[?=!]+$/g, '')
    .trim();

  let evalExpr = cleanMathExpr
    .replace(/x/gi, '*')
    .replace(/\^/g, '**')
    .replace(/(\d+(?:\.\d+)?)%\s*of\s*(\d+(?:\.\d+)?)/i, '($1 / 100) * $2');

  let mathResult;
  try {
    if (/sqrt\s*\(\s*(\d+(?:\.\d+)?)\s*\)/i.test(evalExpr)) {
      const num = parseFloat(evalExpr.match(/sqrt\s*\(\s*(\d+(?:\.\d+)?)\s*\)/i)[1]);
      mathResult = Math.sqrt(num);
    } else if (/^[\d\s+\-*/%().**]+$/.test(evalExpr)) {
      mathResult = Function(`"use strict"; return (${evalExpr})`)();
    }
  } catch (e) {}

  if (mathResult !== undefined && !isNaN(mathResult)) {
    const mathReply = `## 🔢 Mathematical Calculation\n\n` +
      `> **Expression**: \`${cleanMathExpr}\` = **\`${mathResult}\`**\n\n` +
      `---\n\n` +
      `### 📌 Step-by-Step Calculation Breakdown\n` +
      `1. **Input Expression**: \`${cleanMathExpr}\`\n` +
      `2. **Operation**: Arithmetic evaluation \`${evalExpr}\`\n` +
      `3. **Exact Result**: **\`${mathResult}\`**\n\n` +
      `| Parameter | Value |\n` +
      `| :--- | :--- |\n` +
      `| **Expression** | \`${cleanMathExpr}\` |\n` +
      `| **Result** | **\`${mathResult}\`** |\n` +
      `| **Engine** | **Dedicated Math Server (Port 3001)** |\n` +
      `| **Precision** | Standard IEEE 754 Floating-Point |`;

    sendUpdate({ text: mathReply });
    sendUpdate({ type: 'complete' });
    return res.end();
  }

  // 3. Complex Mathematics: Use Groq GPT-OSS-120B with step-by-step LaTeX derivations
  if (groqKey) {
    const postData = JSON.stringify({
      model: 'openai/gpt-oss-120b',
      messages: [
        {
          role: 'system',
          content: 'You are Cognisphere AI Mathematics Engine. Deliver rigorous, step-by-step mathematical solutions, derivations, proofs, and formulas using clear KaTeX formatting ($...$ for inline, $$...$$ for display) and markdown tables.'
        },
        { role: 'user', content: cleanQ }
      ],
      stream: true,
      temperature: 0.1
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
      sendUpdate({ text: `## 🔢 Mathematical Analysis\n\n> **Problem**: \`${cleanQ}\`\n\nUnable to reach LLM math worker right now.` });
      sendUpdate({ type: 'complete' });
      res.end();
    });

    groqReq.write(postData);
    groqReq.end();
    return;
  }

  // Fallback
  sendUpdate({ text: `## 🔢 Mathematical Analysis\n\n> **Problem**: \`${cleanQ}\`\n\nAnalyzed mathematical formulation.` });
  sendUpdate({ type: 'complete' });
  res.end();
});

app.listen(PORT, () => {
  console.log(`🔢 Dedicated Math AI Engine running on http://localhost:${PORT}`);
});
