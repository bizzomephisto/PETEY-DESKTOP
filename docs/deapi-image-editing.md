# deAPI image editing

In Chat, ask PETEY to generate an image from a description. To edit or combine
images, use **+** to attach the files to the same message and describe the
changes. You can select several files at once or add them one at a time. Refer to
**Image 1**, **Image 2**, and so on in the order shown in the composer. PETEY
shows job progress and the finished image in the chat and saves it to Gallery.

Chat requires a configured deAPI key, a chat model that supports tool calls, and
**Allow Petey to control** under **Add-ons → deAPI Media** for the surface you
use. Multi-image chat edits prefer the saved edit model if it accepts all the
attachments and otherwise choose the first compatible model in the account's
deAPI catalog. The upload limit in Chat is 16 attachments totaling 25 MB, with
the same 10 MB per-image limit for editing.

PETEY checks the main prompt, music caption, or speech script against the chosen
deAPI model's catalog limits. Create shows the maximum when a model is selected.
Enhance prompt targets that model's limit and keeps the original in the editor
if the rewrite falls outside it. For MiniMax H3, PETEY uses the
[documented 7,000-character maximum](https://deapi.ai/blog/minimax-h3-prompting-guide-how-to-write-structured-prompts-for-text-to-video)
when the catalog omits it. For other models with no published maximum, PETEY
uses 15,000 characters.

## Create workspace

In Create → Edit / combine images, select a model and add image files or local
browser selections. Images retain the order shown in the list, including mixed
uploads and local browser selections. Refer to the first image, second image,
and so on in the prompt. Remove an individual image to correct a selection.
Gallery's existing image-edit action stages the image in this same list.

PETEY discovers the models available to the configured account. Partner models
appear only when deAPI makes them available to that account. Model information
controls image counts, quality choices, steps, guidance, negative prompt, custom
output dimensions, dimension increments, pixel limits, and aspect ratio limits.
The seed control uses −1 for random generation and accepts 0 as a fixed seed.
Qwen normally retains the input size; its custom size controls stay hidden.
Unsupported fields are omitted from provider requests. Quotes and generation
share the same parameter builder.

Compatibility defaults for currently documented models live in
`petey/deapi_image_models.py`; live catalog metadata overrides them:

| Model slug | Maximum images when not supplied by catalog |
| --- | ---: |
| `Flux_2_Klein_4B_BF16` | 3 |
| `QwenImageEdit_Plus_NF4` | 1 |
| `gpt-image-1.5` | 2 |
| `gpt-image-2` | 2 |
| `gpt-image-2.5` | 16 |
| `nano-banana-2`, `nano-banana-2.1` | 5 |

The API accepts one legacy `source` image or an ordered `references` list, never
both. Each image must be nonempty, at most 10 MB, and JPG/PNG/GIF/BMP/WebP.
The selected model's own count limit is checked again before provider submission.
The edit client uses `/api/v2/images/edits`, a single `image` for one file or
repeated `images[]` fields for multiple files, and v2 job polling. It preserves
filenames and MIME types for references. An unavailable explicitly selected model
fails instead of substituting another model.

Provider image-edit price quotes remain estimates; their documented price endpoint
does not accept uploaded reference images, so actual partner billing can vary with
input images and generated output.

Sources checked 2026-10-14:

- https://docs.deapi.ai/models
- https://docs.deapi.ai/api/v2/images/edits
- https://docs.deapi.ai/api/v2/images/edits-price
- https://deapi.ai/models/flux2-klein-4b-bf16
- https://deapi.ai/models/qwen-image-edit
- https://deapi.ai/models/gpt-image-15
- https://deapi.ai/models/gpt-image-2
- https://deapi.ai/models/gpt-image-25
- https://deapi.ai/models/nano-banana-21

Regression coverage: `tests/test_deapi_image_editing.py`, `test_deapi_client.py`,
`test_media_service.py`, `test_media_jobs.py`, and `test_desktop_app.py`.
