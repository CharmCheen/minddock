# Video Skill Demo

MindDock supports a lightweight video demo path by indexing transcript sidecar files next to local media. This does not add real ASR, browser rendering, ffmpeg, Whisper, cloud transcription, or a video player.

## Supported Media

Video files (`.webm` is treated as video by the current loader):

- `.mp4`
- `.mov`
- `.mkv`
- `.webm`

Audio files:

- `.mp3`
- `.wav`
- `.m4a`
- `.aac`
- `.flac`
- `.ogg`
- `.webm`

## Sidecar Transcript Names

Place the media file and transcript in `knowledge_base` with the same stem.

For `knowledge_base/demo_video.mp4`, MindDock checks sidecars in this order:

```text
knowledge_base/demo_video.transcript.md
knowledge_base/demo_video.transcript.txt
knowledge_base/demo_video.txt
knowledge_base/demo_video.vtt
knowledge_base/demo_video.srt
```

`.srt` and `.vtt` timing, index, header, and cue metadata are stripped before indexing. Meaningful transcript lines are kept. A sidecar transcript is required for a meaningful demo; without one, MindDock falls back to the configured mock/api/disabled media transcription behavior.

When a recognized sidecar is next to a matching media file, MindDock uses it for the media source and skips indexing that sidecar as a separate standalone text source. Ordinary `.txt` and `.md` files that are not sidecars are still indexed normally.

## Ingest

```bash
conda run -n minddock python -m app.demo ingest --no-rebuild
```

After ingest, the video source is indexed using transcript text. In the source drawer, representative metadata should show:

- `Video source`
- `Transcript: sidecar`
- media filename
- sidecar filename

## Skill Resolve Demo

```bash
conda run -n minddock python -m app.demo skill-resolve --source demo_video.mp4
```

The command should resolve to the builtin `video.transcribe` binding when no local manifest overrides it.

## Notes

- Retrieval uses transcript text only.
- Ready video sources remain selectable as normal sources.
- Pending and failed source behavior is unchanged.
- No large media files should be committed to git.
