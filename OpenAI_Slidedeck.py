import os
import re
import json
import ast
import gradio as gr
from fuzzywuzzy import fuzz
from openai import OpenAI
from DOC_REGISTRY import DOC_REGISTRY

client = OpenAI(api_key="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")

def preprocess_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r"\[\d+\]|\(\w+ et al\., \d+\)", "", text)
    text = re.sub(r"\(see Fig\.\s?\d+\)", "", text)
    text = re.sub(r"[*_#]", "", text)
    text = re.sub(r"-\n", "", text)
    return " ".join(text.split())

def read_txt_full_text(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        raw_text = f.read()
    return preprocess_text(raw_text)

def detect_target_doc(query: str, registry: dict, threshold=80):
    query_lower = query.lower()
    best_doc = None
    best_score = 0
    for doc_name, data in registry.items():
        for alias in data["aliases"]:
            score = fuzz.partial_ratio(query_lower, alias.lower())
            if score > best_score:
                best_score = score
                best_doc = doc_name
    return best_doc if best_score >= threshold else None

def gpt_response(system_content, user_prompt, max_tokens=1000):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7,
        max_tokens=max_tokens
    )
    return response.choices[0].message.content

def parse_python_list(raw_output: str) -> list:
    try:
        bracketed = raw_output[raw_output.find("["):raw_output.rfind("]")+1]
        data = ast.literal_eval(bracketed)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []

def generate_slide_deck(full_text: str):
    titles_prompt = f"""
You are an academic presentation assistant. Generate EXACTLY 5 concise slide titles as a Python list based on the following academic content:
Return only the list, no explanation.

Content:
{full_text[:3000]}
"""
    raw_titles = gpt_response("You generate slide titles only.", titles_prompt, 300)
    titles = parse_python_list(raw_titles)
    if len(titles) < 5:
        titles = [f"Slide {i+1}" for i in range(5)]

    slides = []
    for title in titles:
        bullets_prompt = f"""
You are an academic assistant. Generate EXACTLY 3 bullet points as a Python list for the slide titled '{title}' using the content below:
Return only the list.

Content:
{full_text[:3000]}
"""
        raw_bullets = gpt_response("You write 3 bullet points only.", bullets_prompt, 300)
        bullets = parse_python_list(raw_bullets)
        if len(bullets) < 3:
            bullets = ["Point 1", "Point 2", "Point 3"]
        slides.append({"title": title, "bullet_points": bullets})
    return slides

def generate_presentation_code(slides):
    slides_json = json.dumps(slides, indent=2)
    code_prompt = f"""
You are a Python programmer. Generate python code using 'python-pptx' to create a presentation with this content:
{slides_json}

Constraints:
- Use: from pptx import Presentation, from pptx.util import Inches
- First slide = title only; Then for each slide: title + bullet points
- Save as 'presentation.pptx'
- Output ONLY Python code
"""
    raw_code = gpt_response("You generate valid python-pptx code.", code_prompt, 800)
    return raw_code

def handle_user_query(message, chat_history):
    matched_doc = detect_target_doc(message, DOC_REGISTRY)
    if not matched_doc:
        try:
            fallback_response = gpt_response(
                "You are a friendly assistant who only helps users generate slide decks for academic papers they name.",
                f"I couldn't find the paper '{message}'. Can you try a different title, or rephrase it?",
                200
            )
            return fallback_response
        except Exception as e:
            return f"⚠️ Error while handling unknown input: {e}"

    try:
        file_path = f"./papers-cleaned/{matched_doc}.txt"
        full_text = read_txt_full_text(file_path)

        slides = generate_slide_deck(full_text)
        pptx_code = generate_presentation_code(slides)
        return f"🖼️ Slide Deck Data:\n{json.dumps(slides, indent=2)}\n\n💻 PPTX Code:\n```python\n{pptx_code}\n```"

    except Exception as e:
        return f"⚠️ Error: {e}"

chatbot = gr.ChatInterface(
    fn=handle_user_query,
    title="📚 CBS Slide Generator",
    theme="messages",
    chatbot=gr.Chatbot(show_copy_button=True)
)

chatbot.launch()
