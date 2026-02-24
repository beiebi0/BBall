# User Journey

End-to-end flow for turning a raw basketball video into personalized highlight reels.

---

## 1. Open the App

The user opens BBall and lands on the **Home screen**. A prominent **Upload** button is the primary call-to-action.

## 2. Select a Video

Tapping **Upload** opens the iPhone Photos picker. The user selects a basketball game video from their camera roll.

## 3. Upload with Progress

The app requests a **signed GCS upload URL** (`POST /videos/upload-url`) and uploads the video directly to Google Cloud Storage. A progress indicator shows upload percentage. Once the upload completes, the app confirms it (`POST /videos/{video_id}/confirm`), setting the video status to `uploaded`.

## 4. Start Processing

A processing job is created (`POST /jobs`) which publishes a Pub/Sub message to trigger detection and tracking via the subscriber worker (`process_video_detection`). The pipeline first detects the basketball rim position (if configured) for more accurate scoring detection, then runs player and ball detection/tracking. The job status moves through `queued` → `processing`, with `progress` (0-100) and `stage` descriptions updated as the pipeline runs. The app polls `GET /jobs/{job_id}/progress` to display a real-time progress bar.

## 5. Select Your Player

When detection completes, the job transitions to `awaiting_selection`. The app presents an **annotated frame** with detected players highlighted. The user **taps on themselves** to identify which player they are, providing a `player_track_id` (and optionally their team color). This selection is submitted via `POST /jobs/{job_id}/select-player`.

## 6. Highlight Generation

After player selection, the job resumes processing (`process_video_highlights` via Pub/Sub). The progress bar continues updating as the pipeline generates highlight clips.

## 7. Download Highlight Reels

When the job reaches `completed`, the app fetches the results via `GET /highlights?job_id={job_id}`. Two highlight reels are available:

| Highlight Type | Description |
|---|---|
| **Full game** | Best moments from the entire game |
| **Personal** | Clips featuring the selected player |

Each highlight has a **signed download URL**. The user taps **Download** (or **Share**) to save the reel to their camera roll or share it directly.

---

## Status Flow Summary

```
Video:   uploading → uploaded → processing
Job:     queued → processing → awaiting_selection → processing → completed
```
