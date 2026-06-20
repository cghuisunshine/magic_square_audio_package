Files included:

1. magic_square_tutor_script_audio.html
   - Self-contained HTML with one embedded narration control fixed at the bottom of the page.
   - Spoken words highlight during playback.
   - Double-click a spoken word or lesson section to jump the narration to that point.
   - Embedded audio was generated with Microsoft neural speech.

2. generate_magic_square_edge_tts.py
   - Run this in an internet-connected environment to regenerate the same page using Microsoft neural speech.

Commands:
  python -m venv .venv
  .venv/bin/pip install edge-tts
  .venv/bin/python generate_magic_square_edge_tts.py

The script reads magic_square_tutor_script.html from the same folder, outputs magic_square_tutor_script_audio.html, and writes the regenerated MP3/timing files into magic_square_edge_audio/.
