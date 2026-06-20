#!/usr/bin/env python3
# Generate one narrated tutorial track with word timings for highlighting.
# Usage:
#   python -m venv .venv
#   .venv/bin/pip install edge-tts
#   .venv/bin/python generate_magic_square_edge_tts.py

from __future__ import annotations

import asyncio
import base64
import html
import json
import re
from pathlib import Path

import edge_tts


SRC = Path("magic_square_tutor_script.html")
OUT = Path("magic_square_tutor_script_audio.html")
AUDIO_DIR = Path("magic_square_edge_audio")
AUDIO_DIR.mkdir(exist_ok=True)

VOICE = "en-US-JennyNeural"
RATE = "-4%"
TICKS_PER_SECOND = 10_000_000


def seconds(value: int | float | None) -> float:
    return round(float(value or 0) / TICKS_PER_SECOND, 6)


def strip_tags(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"^Say:\s*", "", value, flags=re.I)
    return value.strip("“”\" ")


def normalize_token(value: str) -> str:
    return re.sub(r"\W+", "", value, flags=re.UNICODE).lower()


def find_span(text: str, token: str, cursor: int) -> tuple[int, int]:
    direct = text.lower().find(token.lower(), cursor)
    if direct >= 0:
        return direct, direct + len(token)

    wanted = normalize_token(token)
    if not wanted:
        return cursor, cursor

    for start in range(cursor, len(text)):
        if not text[start].isalnum():
            continue

        collected: list[str] = []
        end = start
        while end < len(text) and len("".join(collected)) < len(wanted):
            if text[end].isalnum():
                collected.append(text[end].lower())
            end += 1

        if "".join(collected) == wanted:
            while end < len(text) and text[end].isalnum():
                end += 1
            return start, end

    return cursor, min(cursor + len(token), len(text))


def build_tutorial_text(scripts: list[str]) -> tuple[str, list[dict[str, int | str]]]:
    parts: list[str] = []
    sections: list[dict[str, int | str]] = []
    cursor = 0

    for index, script in enumerate(scripts):
        if parts:
            parts.append("\n\n")
            cursor += 2

        start = cursor
        parts.append(script)
        cursor += len(script)
        sections.append(
            {
                "index": index,
                "label": f"Section {index + 1:02d}",
                "start_char": start,
                "end_char": cursor,
            }
        )

    return "".join(parts), sections


async def synthesize(full_text: str) -> tuple[Path, list[dict[str, int | float | str]]]:
    mp3 = AUDIO_DIR / "magic_square_tutorial.mp3"
    words: list[dict[str, int | float | str]] = []
    cursor = 0

    communicate = edge_tts.Communicate(full_text, voice=VOICE, rate=RATE, boundary="WordBoundary")
    with mp3.open("wb") as audio_file:
        async for message in communicate.stream():
            kind = message.get("type")
            if kind == "audio":
                audio_file.write(message["data"])
            elif kind == "WordBoundary":
                spoken = message.get("text", "")
                start_char, end_char = find_span(full_text, spoken, cursor)
                cursor = max(cursor, end_char)
                start = seconds(message.get("offset"))
                duration = seconds(message.get("duration"))
                words.append(
                    {
                        "text": spoken,
                        "start": start,
                        "end": round(start + duration, 6),
                        "duration": duration,
                        "start_char": start_char,
                        "end_char": end_char,
                    }
                )

    return mp3, words


def assign_sections(
    words: list[dict[str, int | float | str]],
    sections: list[dict[str, int | str]],
) -> None:
    for word_index, word in enumerate(words):
        word["index"] = word_index
        for section in sections:
            section_start = int(section["start_char"])
            section_end = int(section["end_char"])
            word_start = int(word["start_char"])
            if section_start <= word_start < section_end:
                word["section"] = int(section["index"])
                word["local_start"] = word_start - section_start
                word["local_end"] = int(word["end_char"]) - section_start
                break

    for section in sections:
        section_words = [word for word in words if word.get("section") == section["index"]]
        section["start"] = float(section_words[0]["start"]) if section_words else 0
        section["end"] = float(section_words[-1]["end"]) if section_words else float(section["start"])


def render_timed_text(script: str, words: list[dict[str, int | float | str]]) -> str:
    pieces: list[str] = []
    cursor = 0

    for word in words:
        start = int(word["local_start"])
        end = int(word["local_end"])
        if start > cursor:
            pieces.append(html.escape(script[cursor:start]))

        pieces.append(
            '<span class="tts-word" '
            f'data-word-index="{int(word["index"])}" '
            f'data-start="{float(word["start"]):.6f}">'
            f"{html.escape(script[start:end])}</span>"
        )
        cursor = end

    if cursor < len(script):
        pieces.append(html.escape(script[cursor:]))

    return "".join(pieces)


def player_css() -> str:
    return """
  body{padding-bottom:104px}
  .step{scroll-margin-bottom:130px}
  .step[data-start-time]{cursor:pointer}
  .step.is-current{border-color:#111827;box-shadow:0 2px 8px rgba(15,23,42,.08)}
  .section-head{display:flex;align-items:center;gap:8px;margin-bottom:6px}
  .section-head .num{margin-bottom:0;flex:1}
  .section-speak-button{appearance:none;border:1px solid #d1d5db;background:#fff;color:#111827;width:30px;height:30px;border-radius:8px;display:inline-flex;align-items:center;justify-content:center;cursor:pointer;flex:0 0 auto}
  .section-speak-button:hover{background:#f3f4f6;border-color:#9ca3af}
  .section-speak-button:focus-visible{outline:2px solid #111827;outline-offset:2px}
  .section-speak-button svg{width:16px;height:16px;display:block}
  .section-speak-button .section-icon-pause{display:none}
  .step.is-speaking-section .section-icon-play{display:none}
  .step.is-speaking-section .section-icon-pause{display:block}
  .say{cursor:text}
  .narration-text{cursor:pointer}
  .tts-word{border-radius:3px;transition:background-color 120ms ease,color 120ms ease}
  .tts-word.is-speaking{background:#facc15;color:#111827}
  .tutorial-player{position:fixed;left:0;right:0;bottom:0;z-index:20;background:#ffffff;border-top:1px solid #d1d5db;box-shadow:0 -2px 8px rgba(15,23,42,.08)}
  .player-inner{max-width:1040px;margin:0 auto;padding:12px 18px;display:grid;grid-template-columns:minmax(160px,240px) 1fr;gap:16px;align-items:center}
  .player-title{font-size:.9rem;font-weight:800;color:#111827;line-height:1.35}
  .player-status{font-size:.82rem;color:#4b5563;line-height:1.35;margin-top:2px}
  .tutorial-player audio{width:100%;height:36px}
  @media(max-width:720px){body{padding-bottom:132px}.player-inner{grid-template-columns:1fr;gap:8px}.player-title{font-size:.86rem}}
"""


def player_script(timing_payload: dict[str, object]) -> str:
    payload_json = json.dumps(timing_payload, ensure_ascii=False)
    return f"""
<script>
const TUTORIAL_TIMINGS = {payload_json};

const audio = document.getElementById("tutorial-audio");
const playerTitle = document.getElementById("player-title");
const playerStatus = document.getElementById("player-status");
const wordSpans = Array.from(document.querySelectorAll(".tts-word"));
const sections = Array.from(document.querySelectorAll(".step[data-start-time]"));
const sectionButtons = Array.from(document.querySelectorAll(".section-speak-button"));
let activeWord = -1;
let activeSection = -1;
let pauseAfterSection = null;
let rafId = null;

function findActiveWord(time) {{
  let low = 0;
  let high = TUTORIAL_TIMINGS.words.length - 1;
  while (low <= high) {{
    const mid = Math.floor((low + high) / 2);
    const word = TUTORIAL_TIMINGS.words[mid];
    if (time < word.start) high = mid - 1;
    else if (time >= word.end) low = mid + 1;
    else return mid;
  }}
  return -1;
}}

function setActiveSection(index, shouldScroll) {{
  if (index === activeSection) return;
  if (activeSection >= 0) sections[activeSection]?.classList.remove("is-current");
  activeSection = index;
  const section = sections[index];
  if (!section) return;
  section.classList.add("is-current");
  playerTitle.textContent = section.dataset.sectionLabel || "Narration";
  playerStatus.textContent = section.querySelector("h2")?.textContent || "";
  if (shouldScroll) section.scrollIntoView({{ block: "center", behavior: "smooth" }});
}}

function sectionIndexForTime(time) {{
  const current = TUTORIAL_TIMINGS.sections.findIndex((section) => (
    time >= section.start - 0.25 && time < section.end
  ));
  if (current >= 0) return current;
  return TUTORIAL_TIMINGS.sections.findIndex((section) => time < section.start);
}}

function syncSectionButtons() {{
  const playingIndex = (!audio.paused && !audio.ended) ? sectionIndexForTime(audio.currentTime) : -1;
  sections.forEach((section, index) => {{
    const button = sectionButtons[index];
    const isSpeaking = index === playingIndex;
    section.classList.toggle("is-speaking-section", isSpeaking);
    if (!button) return;
    const label = section.dataset.sectionLabel || `Section ${{index + 1}}`;
    button.setAttribute("aria-label", `${{isSpeaking ? "Pause" : "Play"}} ${{label}}`);
    button.title = isSpeaking ? "Pause this section" : "Play this section";
  }});
}}

function checkSectionPause() {{
  if (pauseAfterSection === null || audio.paused || audio.ended) return;
  const section = TUTORIAL_TIMINGS.sections[pauseAfterSection];
  if (!section) return;
  if (audio.currentTime >= section.end - 0.04) {{
    audio.currentTime = section.end;
    audio.pause();
    pauseAfterSection = null;
  }}
}}

function paint(shouldScroll = false) {{
  const nextWord = findActiveWord(audio.currentTime);
  if (nextWord !== activeWord) {{
    if (activeWord >= 0) wordSpans[activeWord]?.classList.remove("is-speaking");
    activeWord = nextWord;
    if (activeWord >= 0) {{
      wordSpans[activeWord]?.classList.add("is-speaking");
      const sectionIndex = Number(TUTORIAL_TIMINGS.words[activeWord].section);
      if (!Number.isNaN(sectionIndex)) setActiveSection(sectionIndex, shouldScroll);
    }}
  }}
  syncSectionButtons();
}}

function tick() {{
  paint(true);
  checkSectionPause();
  if (!audio.paused && !audio.ended) rafId = requestAnimationFrame(tick);
}}

function seekTo(time, sectionIndex = null) {{
  pauseAfterSection = sectionIndex ?? sectionIndexForTime(time);
  audio.currentTime = Math.max(0, time);
  paint(true);
  audio.play().catch(() => {{}});
}}

function toggleSectionPlayback(section, index) {{
  const start = Number(section.dataset.startTime || 0);
  const end = Number(TUTORIAL_TIMINGS.sections[index]?.end || start);
  const isCurrentSectionTime = audio.currentTime >= start - 0.25 && audio.currentTime < end;
  if (isCurrentSectionTime && !audio.paused && !audio.ended) {{
    audio.pause();
    pauseAfterSection = null;
    return;
  }}
  seekTo(start, index);
}}

wordSpans.forEach((span) => {{
  span.addEventListener("dblclick", (event) => {{
    event.stopPropagation();
    seekTo(Number(span.dataset.start || 0), sectionIndexForTime(Number(span.dataset.start || 0)));
  }});
}});

sections.forEach((section, index) => {{
  section.addEventListener("dblclick", () => toggleSectionPlayback(section, index));
  section.addEventListener("click", () => setActiveSection(index, false));
}});

sectionButtons.forEach((button, index) => {{
  button.addEventListener("click", (event) => {{
    event.preventDefault();
    event.stopPropagation();
    if (event.detail > 1) return;
    const section = sections[index];
    if (section) toggleSectionPlayback(section, index);
  }});
  button.addEventListener("dblclick", (event) => {{
    event.preventDefault();
    event.stopPropagation();
  }});
}});

audio.addEventListener("play", () => {{
  if (pauseAfterSection === null) pauseAfterSection = sectionIndexForTime(audio.currentTime);
  if (rafId) cancelAnimationFrame(rafId);
  tick();
}});
audio.addEventListener("pause", () => {{
  if (rafId) cancelAnimationFrame(rafId);
  rafId = null;
  syncSectionButtons();
}});
audio.addEventListener("timeupdate", () => {{
  paint(false);
  checkSectionPause();
}});
audio.addEventListener("seeked", () => {{
  paint(true);
  checkSectionPause();
}});
audio.addEventListener("ended", () => {{
  if (activeWord >= 0) wordSpans[activeWord]?.classList.remove("is-speaking");
  activeWord = -1;
  syncSectionButtons();
}});

setActiveSection(0, false);
syncSectionButtons();
</script>
"""


def section_speak_button(index: int, label: str) -> str:
    safe_label = html.escape(label, quote=True)
    return (
        f'<button class="section-speak-button" type="button" '
        f'aria-label="Play {safe_label}" title="Play this section" '
        f'data-section-index="{index}">'
        '<svg class="section-icon-play" viewBox="0 0 24 24" aria-hidden="true">'
        '<path fill="currentColor" d="M8 5v14l11-7z"/></svg>'
        '<svg class="section-icon-pause" viewBox="0 0 24 24" aria-hidden="true">'
        '<path fill="currentColor" d="M7 5h4v14H7zm6 0h4v14h-4z"/></svg>'
        "</button>"
    )


def build_html(
    source: str,
    scripts: list[str],
    sections: list[dict[str, int | float | str]],
    words: list[dict[str, int | float | str]],
    mp3: Path,
) -> str:
    timing_payload = {
        "sections": [
            {
                "label": section["label"],
                "start": section["start"],
                "end": section["end"],
            }
            for section in sections
        ],
        "words": [
            {
                "start": word["start"],
                "end": word["end"],
                "section": word.get("section", -1),
            }
            for word in words
        ],
    }

    words_by_section: list[list[dict[str, int | float | str]]] = []
    for section in sections:
        words_by_section.append([word for word in words if word.get("section") == section["index"]])

    audio_b64 = base64.b64encode(mp3.read_bytes()).decode("ascii")
    player = f"""
<div class="tutorial-player" role="region" aria-label="Narration player">
  <div class="player-inner">
    <div>
      <div class="player-title" id="player-title">Narration</div>
      <div class="player-status" id="player-status"></div>
    </div>
    <audio id="tutorial-audio" controls preload="metadata" src="data:audio/mpeg;base64,{audio_b64}"></audio>
  </div>
</div>
"""

    source = source.replace(
        "  .say{background:#f8fafc;border-left:4px solid #94a3b8;border-radius:12px;padding:12px 14px;margin:10px 0}\n",
        "  .say{background:#f8fafc;border-left:4px solid #94a3b8;border-radius:12px;padding:12px 14px;margin:10px 0}\n"
        + player_css(),
    )

    section_matches = list(re.finditer(r'<section class="step( final)?">', source))
    rebuilt: list[str] = []
    last = 0
    for index, match in enumerate(section_matches):
        section = sections[index]
        attrs = (
            f'<section class="step{match.group(1) or ""}" '
            f'data-section-index="{index}" '
            f'data-section-label="{html.escape(str(section["label"]))}" '
            f'data-start-time="{float(section["start"]):.6f}">'
        )
        rebuilt.append(source[last : match.start()])
        rebuilt.append(attrs)
        last = match.end()
    rebuilt.append(source[last:])
    source = "".join(rebuilt)

    say_matches = list(re.finditer(r'<div class="say">(.*?)</div>', source, flags=re.S))
    rebuilt = []
    last = 0
    for index, match in enumerate(say_matches):
        script = scripts[index]
        timed_text = render_timed_text(script, words_by_section[index])
        replacement = (
            f'<div class="say" data-section-index="{index}">'
            f'<strong>Say:</strong> “<span class="narration-text">{timed_text}</span>”'
            "</div>"
        )
        rebuilt.append(source[last : match.start()])
        rebuilt.append(replacement)
        last = match.end()
    rebuilt.append(source[last:])
    source = "".join(rebuilt)

    num_matches = list(re.finditer(r'<div class="num">(.*?)</div>', source, flags=re.S))
    rebuilt = []
    last = 0
    for index, match in enumerate(num_matches):
        label = str(sections[index]["label"]) if index < len(sections) else f"Section {index + 1:02d}"
        replacement = (
            '<div class="section-head">'
            f"{match.group(0)}"
            f"{section_speak_button(index, label)}"
            "</div>"
        )
        rebuilt.append(source[last : match.start()])
        rebuilt.append(replacement)
        last = match.end()
    rebuilt.append(source[last:])
    source = "".join(rebuilt)

    source = source.replace("</body>", player + player_script(timing_payload) + "\n</body>")
    return source


async def main() -> None:
    source = SRC.read_text(encoding="utf-8")
    say_blocks = list(re.finditer(r'<div class="say">(.*?)</div>', source, flags=re.S))
    scripts = [strip_tags(match.group(1)) for match in say_blocks]
    full_text, sections = build_tutorial_text(scripts)

    print("Generating magic_square_edge_audio/magic_square_tutorial.mp3")
    mp3, words = await synthesize(full_text)
    assign_sections(words, sections)

    timing_json = AUDIO_DIR / "magic_square_tutorial.words.json"
    timing_json.write_text(
        json.dumps(
            {
                "text": full_text,
                "voice": VOICE,
                "audio": mp3.name,
                "sections": sections,
                "words": words,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    OUT.write_text(build_html(source, scripts, sections, words, mp3), encoding="utf-8")
    print(f"Wrote {OUT}")
    print(f"Wrote {timing_json}")


if __name__ == "__main__":
    asyncio.run(main())
