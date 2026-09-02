from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import os, time, re, json, base64
import concurrent.futures
from dotenv import load_dotenv
from ddgs import DDGS
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

try:
    from groq import Groq as GroqClient
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(_env_path, override=True)


app = FastAPI(title="WorldBrain Quantum AI - Backend", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    query: str
    user_id: Optional[str] = "anonymous"
    tool: Optional[str] = None


class ShareRequest(BaseModel):
    conversation: dict


class ImageGenRequest(BaseModel):
    prompt: str


# ── Model fallback chain ──────────────────────────────────────────────────────
GROQ_MODELS = [
    "llama-3.1-8b-instant",
    "llama3-8b-8192",
    "gemma2-9b-it",
    "llama-3.3-70b-versatile",
    "mixtral-8x7b-32768",
]

GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
]


def stream_with_fallback(messages: list, temperature: float = 0.4):
    """Try Groq first (Llama 3 — fast + free), then fall back to Gemini rapidly."""

    groq_key = os.getenv("GROQ_API_KEY", "").strip()

    # ── 1. Groq (primary multi-model cluster) ─────────────────────────────────
    if GROQ_AVAILABLE and groq_key:
        groq_msgs = []
        for m in messages:
            if isinstance(m, SystemMessage):
                groq_msgs.append({"role": "system", "content": m.content})
            elif isinstance(m, HumanMessage):
                groq_msgs.append({"role": "user", "content": m.content})

        for model_name in GROQ_MODELS:
            try:
                print(f"Groq worker trying {model_name}")
                client = GroqClient(api_key=groq_key, timeout=4.0)
                stream = client.chat.completions.create(
                    model=model_name,
                    messages=groq_msgs,
                    temperature=temperature,
                    max_tokens=2048,
                    stream=True,
                )
                yielded = False
                for chunk in stream:
                    delta = chunk.choices[0].delta.content or ""
                    if delta:
                        yield delta
                        yielded = True
                if yielded:
                    print(f"Groq worker success: {model_name}")
                    return
            except Exception as e:
                err = str(e)
                print(f"Groq {model_name} error: {err[:120]}")
                continue

    # ── 2. Gemini fallback ───────────────────────────────────────────────────
    api_key = os.getenv("GOOGLE_API_KEY", "")
    for model_name in GEMINI_MODELS:
        try:
            print(f"Gemini worker trying {model_name}")
            llm = ChatGoogleGenerativeAI(
                model=model_name,
                temperature=temperature,
                google_api_key=api_key,
                request_timeout=8.0,
                streaming=True,
            )
            for chunk in llm.stream(messages):
                content = chunk.content
                if isinstance(content, list):
                    for part in content:
                        yield part.get("text", "") if isinstance(part, dict) else str(part)
                else:
                    yield str(content)
            return
        except Exception as e:
            err_str = str(e)
            print(f"Gemini {model_name} failed: {err_str[:120]}")
            continue

    yield "All AI providers are busy right now. Please retry in a few seconds."


def invoke_with_fallback(messages: list, temperature: float = 0.4) -> str:
    return "".join(stream_with_fallback(messages, temperature))


# ── Media helpers ─────────────────────────────────────────────────────────────

def fetch_images(query: str, max_results: int = 6) -> list:
    try:
        with DDGS() as ddgs:
            raw_imgs = list(ddgs.images(query, max_results=max_results))
            media_items = []
            for img in raw_imgs:
                full_url = img.get("image") or img.get("url") or ""
                thumb_url = img.get("thumbnail") or full_url
                title = img.get("title", "Image")
                if full_url:
                    media_items.append({"url": full_url, "thumb": thumb_url, "title": title, "type": "image"})
            return media_items
    except Exception as e:
        print(f"Image search error: {e}")
        return []


def fetch_videos(query: str, max_results: int = 10) -> list:
    edu_query = f"{query} tutorial explained"
    try:
        with DDGS() as ddgs:
            raw_vids = list(ddgs.videos(edu_query, max_results=max_results))
            media_items = []
            for vid in raw_vids:
                url = vid.get("content") or vid.get("url") or vid.get("href", "")
                title = vid.get("title", "Video")
                video_id = None
                yt_match = re.search(r"(?:v=|youtu\.be/|embed/)([A-Za-z0-9_-]{11})", url)
                if yt_match:
                    video_id = yt_match.group(1)
                thumb = vid.get("images", {}).get("large") or vid.get("images", {}).get("medium") or ""
                if video_id and not thumb:
                    thumb = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
                if url:
                    media_items.append({"url": url, "video_id": video_id, "thumb": thumb, "title": title, "type": "video"})
            return media_items
    except Exception as e:
        print(f"Video search error: {e}")

    # Fallback text search for YouTube
    try:
        with DDGS() as ddgs:
            raw_text = list(ddgs.text(f"site:youtube.com {query} tutorial", max_results=10))
            media_items = []
            for vid in raw_text:
                url = vid.get("href", "")
                yt_match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", url)
                if yt_match:
                    video_id = yt_match.group(1)
                    thumb = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
                    media_items.append({"url": url, "video_id": video_id, "thumb": thumb, "title": vid.get("title", "Video"), "type": "video"})
            return media_items
    except Exception as e:
        print(f"Video fallback error: {e}")
        return []


# ── Quality scoring for search results ───────────────────────────────────────

TRUSTED_DOMAINS = {
    "wikipedia.org": 10, "github.com": 9, "stackoverflow.com": 9,
    "docs.python.org": 9, "developer.mozilla.org": 9, "medium.com": 7,
    "arxiv.org": 8, "pubmed.ncbi.nlm.nih.gov": 9, "nature.com": 9,
    "sciencedirect.com": 8, "britannica.com": 8, "bbc.com": 7,
    "reuters.com": 8, "techcrunch.com": 7, "wired.com": 7,
    "geeksforgeeks.org": 8, "towardsdatascience.com": 7, "realpython.com": 9,
    "docs.microsoft.com": 9, "learn.microsoft.com": 9, "oracle.com": 8,
    "aws.amazon.com": 8, "cloud.google.com": 8, "w3schools.com": 7,
    "youtube.com": 6, "reddit.com": 5, "quora.com": 4,
}

LOW_QUALITY = ["ad.", "ads.", "popup", "clickbait", "spam"]


def score_search_result(r: dict) -> int:
    """Score a search result by domain trust + snippet length."""
    url = r.get("href") or r.get("url") or r.get("link") or ""
    snippet = r.get("body") or r.get("snippet") or ""
    title = r.get("title") or ""

    # Base score from domain trust
    score = 0
    for domain, trust in TRUSTED_DOMAINS.items():
        if domain in url:
            score += trust
            break

    # Bonus for longer, more detailed snippets
    score += min(len(snippet) // 80, 5)

    # Bonus for longer titles (more descriptive)
    score += min(len(title) // 20, 3)

    # Penalise low-quality patterns
    for bad in LOW_QUALITY:
        if bad in url.lower():
            score -= 5

    return score


def rank_results(results: list) -> list:
    """Sort results by quality score descending."""
    return sorted(results, key=score_search_result, reverse=True)


# ── Universal Smart Prompt Builder ───────────────────────────────────────────

def build_smart_prompt(query: str, has_search: bool = True) -> str:
    """
    Build a world-class system prompt for any domain or language.
    Web search is ALWAYS on — has_search defaults to True.
    Never forces a specific coding language — always matches the user's request.
    """
    q = query.lower()

    base = (
        "You are WorldBrain — a world-class AI search engine and knowledge assistant. "
        "You have access to real-time web search results. "
        "Whatever the user asks, ALWAYS provide a SIMPLE, CRISP, DIRECT, and HIGHLY MEANINGFUL answer. "
        "Use easy-to-understand language with maximum clarity and core depth. "
        "Answer EVERY question regardless of domain: science, technology, medicine, law, history, "
        "mathematics, economics, arts, sports, coding (any language), general knowledge, and more. "
        "NEVER refuse to answer. NEVER say you cannot help. "
        "Get straight to the answer without fluff, verbose chatter, or convoluted jargon. "
        "Organize answers cleanly using bold terms, simple bullet points, markdown tables, or working code blocks. "
        "Use the web search results to add real facts, cite as [Source Title](URL)."
    )

    ctx = "\n\nYou have LIVE WEB SEARCH RESULTS. Use them. Cite as [Title](URL). " if has_search else ""

    # ── Code / Implementation ────────────────────────────────────────────────
    if any(kw in q for kw in ['code', 'implement', 'function', 'program', 'script',
                               'write a', 'example', 'how to build', 'create a',
                               'algorithm', 'syntax', 'debug', 'error in', 'fix this']):
        # Detect language from query — never force Python or any specific language
        lang_hint = ""
        for lang in ['python', 'javascript', 'typescript', 'java', 'c++', 'c#', 'rust',
                     'go', 'kotlin', 'swift', 'ruby', 'php', 'sql', 'bash', 'r ', 'dart',
                     'scala', 'haskell', 'lua', 'perl', 'matlab', 'html', 'css']:
            if lang in q:
                lang_hint = f" Write the code in {lang.strip().upper()}."
                break
        return (base + ctx +
            f"The user wants CODE or a PROGRAMMING solution.{lang_hint} Structure as:\n"
            "1. **Complete working code** in a correctly labelled fenced code block\n"
            "2. **Brief explanation** of what the code does (2-4 lines)\n"
            "3. **Usage example** if helpful\n"
            "Match the language the user asked for. If no language specified, use the most appropriate one.")

    # ── Comparison / Difference ──────────────────────────────────────────────
    if any(kw in q for kw in ['difference', 'vs', 'versus', 'compare', 'better than',
                               'pros and cons', 'advantages', 'disadvantages']):
        return (base + ctx +
            "The user wants a COMPARISON. Structure as:\n"
            "1. **One-line summary** of the key difference\n"
            "2. A **markdown TABLE** — rows = criteria, columns = items being compared\n"
            "3. **Pros & Cons** for each in bullet points\n"
            "4. **Recommendation** — which to use and when")

    # ── Diagram / Flow / Process ─────────────────────────────────────────────
    if any(kw in q for kw in ['diagram', 'flowchart', 'flow chart', 'architecture',
                               'process of', 'steps to', 'workflow', 'pipeline', 'how does']):
        return (base + ctx +
            "The user wants a DIAGRAM or PROCESS. Structure as:\n"
            "1. **Overview** (2-3 lines)\n"
            "2. A **Mermaid diagram** inside ```mermaid ... ``` that visualises the flow\n"
            "   Use: graph TD, sequenceDiagram, or flowchart LR\n"
            "3. **Step-by-step explanation** numbered\n"
            "4. **Key concepts** bullet list")

    # ── Math / Calculation ───────────────────────────────────────────────────
    if any(kw in q for kw in ['calculate', 'solve', 'equation', 'formula', 'math',
                               'integral', 'derivative', 'matrix', 'probability', 'statistics']):
        return (base + ctx +
            "The user wants MATH / CALCULATION. Structure as:\n"
            "1. **Formula / equation** shown clearly\n"
            "2. **Step-by-step solution** with numbered steps\n"
            "3. **Final answer** bolded\n"
            "4. **Explanation** of each step in plain English")

    # ── List / Top N ─────────────────────────────────────────────────────────
    if any(kw in q for kw in ['list', 'top', 'best', 'types of', 'kinds of', 'examples',
                               'ways to', 'methods', 'tools for', 'apps for', 'resources']):
        return (base + ctx +
            "The user wants a LIST or TOP-N. Structure as:\n"
            "1. **Brief intro** (1 sentence)\n"
            "2. Numbered list — **bold name** + short description for each\n"
            "3. **Comparison table** if 4+ items\n"
            "4. **Bottom line** recommendation")

    # ── Definition / Explanation ─────────────────────────────────────────────
    if any(kw in q for kw in ['what is', 'what are', 'explain', 'define', 'meaning',
                               'tell me about', 'describe', 'who is', 'where is', 'when did']):
        return (base + ctx +
            "The user wants an EXPLANATION. Structure as:\n"
            "1. **Definition** — one clear sentence\n"
            "2. **How it works / Background** — 2-4 short paragraphs with ## headers\n"
            "3. **Real-world examples** in a bullet list\n"
            "4. **Key facts** table if applicable\n"
            "Use **bold** for key terms.")

    # ── General / Research ───────────────────────────────────────────────────
    return (base + ctx +
        "Give a direct, well-structured answer:\n"
        "1. Start with a **clear direct answer**\n"
        "2. Use ## headers to organise sections\n"
        "3. Use **bold**, bullet lists, and tables where helpful\n"
        "4. End with a **Summary** section\n"
        "Be thorough, accurate, and use the web search results for up-to-date facts.")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "WorldBrain Quantum AI v3", "models": GEMINI_MODELS}


@app.post("/api/generate-image")
async def generate_image_endpoint(req: ImageGenRequest):
    """
    Generate an image using Gemini Imagen.
    Returns base64 image data — no AI branding included.
    """
    try:
        import google.generativeai as genai
        api_key = os.getenv("GOOGLE_API_KEY", "")
        genai.configure(api_key=api_key)

        # Use Imagen 3 for image generation
        model = genai.ImageGenerationModel("imagen-3.0-generate-001")
        response = model.generate_images(
            prompt=req.prompt,
            number_of_images=1,
            aspect_ratio="16:9",
        )

        if response.images:
            img = response.images[0]
            img_bytes = img._pil_image.tobytes() if hasattr(img, '_pil_image') else None
            if img_bytes:
                b64 = base64.b64encode(img_bytes).decode("utf-8")
                return {"image": b64, "format": "jpeg"}

        return {"error": "No image generated"}
    except Exception as e:
        print(f"Image generation error: {e}")
        # Fallback: search for a relevant image via DuckDuckGo
        try:
            with DDGS() as ddgs:
                imgs = list(ddgs.images(req.prompt, max_results=1))
                if imgs:
                    return {"image_url": imgs[0].get("image", ""), "fallback": True}
        except:
            pass
        return {"error": str(e)}


@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):

    async def event_generator():

        # ── WEB SEARCH — ALWAYS ON for every query ───────────────────────────
        # Every question goes through web search in background for the best answers
        q_lower = request.query.lower()
        wants_images = any(kw in q_lower for kw in [
            'image', 'photo', 'picture', 'pic', 'show', 'visual',
            'poster', 'wallpaper', 'thumbnail', 'generate image',
            'create image', 'make image', 'draw'
        ])

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)

        def get_text_results(q):
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(q, max_results=8))
                    return rank_results(results)  # Quality ranked
            except Exception as e:
                print(f"Text search error: {e}")
                return []

        # Always search in background
        future_text   = executor.submit(get_text_results, request.query)
        future_images = executor.submit(fetch_images, request.query, 5) if wants_images else None
        future_videos = executor.submit(fetch_videos, request.query, 10)

        # Wait max 1.5s for quick context
        import asyncio
        try:
            quick_results = future_text.result(timeout=1.5)
        except Exception:
            quick_results = []

        print(f"Quick search: {len(quick_results)} results — starting AI stream")

        # Build prompt with live web context
        if quick_results:
            context_parts = []
            for r in quick_results[:5]:
                context_parts.append(
                    "Title: " + r.get("title", "") + "\n" +
                    "URL: " + str(r.get("href") or r.get("url") or r.get("link") or "") + "\n" +
                    "Snippet: " + r.get("body", "")
                )
            search_context = "\n\n---\n\n".join(context_parts)
            system_prompt = build_smart_prompt(request.query, has_search=True)
            user_prompt = (
                "**Question:** " + request.query + "\n\n"
                "**Live Web Search Results:**\n\n" + search_context + "\n\n"
                "Answer now. Cite facts as [Title](URL). Be comprehensive and accurate."
            )
        else:
            system_prompt = build_smart_prompt(request.query, has_search=False)
            user_prompt = request.query

        # ── Stream AI tokens ─────────────────────────────────────────────────
        try:
            for token in stream_with_fallback(
                [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
            ):
                yield json.dumps({"type": "token", "content": token}) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "content": str(e)}) + "\n"

        # ── Collect remaining search results & media ─────────────────────────
        media_list = []
        try:
            all_results = future_text.result(timeout=1) if not future_text.done() else quick_results
        except Exception:
            all_results = quick_results

        if future_images:
            try:
                media_list.extend(future_images.result(timeout=1))
            except Exception:
                pass
        if future_videos:
            try:
                media_list.extend(future_videos.result(timeout=1))
            except Exception:
                pass

        executor.shutdown(wait=False)

        # Send media + ranked sources to frontend
        if media_list or all_results:
            yield json.dumps({
                "type": "media",
                "media": media_list,
                "searchResults": all_results[:6],  # Top 6 quality-ranked results
            }) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")


# ── Share Endpoints ───────────────────────────────────────────────────────────

import uuid

SHARED_CHATS_FILE = "shared_chats.json"


@app.post("/api/share")
def create_shared_chat(req: ShareRequest):
    try:
        if os.path.exists(SHARED_CHATS_FILE):
            with open(SHARED_CHATS_FILE, "r", encoding="utf-8") as f:
                chats = json.load(f)
        else:
            chats = {}

        share_id = str(uuid.uuid4())[:8]
        chats[share_id] = req.conversation

        with open(SHARED_CHATS_FILE, "w", encoding="utf-8") as f:
            json.dump(chats, f)

        return {"share_id": share_id}
    except Exception as e:
        print(f"Error saving share: {e}")
        return {"error": "Failed to create share link"}


@app.get("/api/share/{share_id}")
def get_shared_chat(share_id: str):
    if not os.path.exists(SHARED_CHATS_FILE):
        return {"error": "Chat not found"}
    try:
        with open(SHARED_CHATS_FILE, "r", encoding="utf-8") as f:
            chats = json.load(f)
        if share_id in chats:
            return {"conversation": chats[share_id]}
        else:
            return {"error": "Chat not found"}
    except Exception as e:
        print(f"Error reading share: {e}")
        return {"error": "Failed to retrieve chat"}
