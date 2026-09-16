# First-review walkthrough

The 30-second animation and video show four **actual interface states** with
explanatory captions. They are an annotated walkthrough of saved scripted
Docker controls, not a real-time recording of an agent run.

| Time | View | Finding |
| --- | --- | --- |
| 0–7.5 s | Revision comparison | The score rises from 90% to 93.75%. Two closure checks improve; the notes check regresses. |
| 7.5–15 s | `retry-after-commit`, step 3 | The note is committed before the tool returns `temporarily_unavailable`. |
| 15–22.5 s | The same case, step 4 | A retry with a different idempotency key adds the note again. |
| 22.5–30 s | Suite acceptance rules | The same 93.75% policy passes a permissive gate and fails the strict notes gate. |

The MP4 has controls, optional captions and no audio or autoplay. The README
uses a GIF and selects a static image for reduced-motion preferences.

## Reproduce the media

Use the repository's Python development environment, installed npm
dependencies and Playwright Chromium. The capture also requires an FFmpeg
executable with libx264 and GIF encoding support.

```bash
python scripts/build_site.py --output dist/media-source
python -m http.server 8767 --bind 127.0.0.1 --directory dist/media-source
```

In a second terminal, from the same repository:

```bash
SITE_URL=http://127.0.0.1:8767/ FFMPEG=ffmpeg node scripts/capture_first_review.cjs
```

The script asserts the displayed scores, regression count, committed error,
duplicate note and gate decisions before taking screenshots. It adds captions
in a separate composition and writes `docs/assets/first-review.*`.
`first-review-media.json` records media hashes and the original evidence hashes.
Font and encoder differences may change media bytes. The original evidence
is never rewritten.

Rebuild the site into a fresh directory to include regenerated media. Read the
[first-review guide](first-review.md) for the actual offline verification
steps and their limits.
