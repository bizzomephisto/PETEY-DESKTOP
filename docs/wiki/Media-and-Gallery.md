# Media and Gallery

PETEY uses deAPI for media creation. Save a deAPI key before starting a job.

## Available work

- Generate or restyle images
- Generate video or animate an image
- Restyle video
- Generate music
- Generate speech
- Remove image backgrounds
- Upscale images or video when supported by the selected model

## Create images from Chat

Enable **Allow Petey to control** for **deAPI Media** in Addons and use a chat
model that supports tool calls. Ask PETEY to generate an image, or attach
images to the same message and ask PETEY to edit or combine them. Reference
the images in the order shown in the composer. Results appear in Chat and
Gallery.

## Create media

1. Open **Media**.
2. Choose an operation and model.
3. Enter a prompt and add any required input file.
4. Check the selected model's prompt limit and review the estimate when available.
5. Submit the job and watch its progress.

Media jobs run in a queue and may take time. A queued job has been accepted but is
not complete. PETEY can run several jobs in parallel.

## Gallery

Completed work is captured in PETEY's local Gallery. From there you can preview,
open with the operating system's default application, or save a copy elsewhere.
FFmpeg is required for browser-compatible previews of some generated videos.

Generation uses provider credits. Check PETEY's displayed balance and the provider's
current pricing and limits before submitting large jobs.
