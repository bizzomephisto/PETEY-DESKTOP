"""Local-only Flask application used by Petey's desktop window."""

from __future__ import annotations

import asyncio
import json
from pathlib import PurePath

from flask import Flask, jsonify, render_template, request, send_file, url_for

from petey.assistant import AssistantAttachment, AssistantIdentity, AssistantService, PETEY_USER_ID
from petey.ai_provider import AIProvider, AIProviderError
from petey.config import PERSONA_PRESETS
from petey.desktop_state import DesktopState
from petey.desktop_memory import DesktopMemory
from petey.media_service import MediaInput, MediaService
from petey.media_jobs import MediaGallery, MediaJobManager
from petey.workspace import WorkspaceError, WorkspaceService
from petey.image_browser import ImageBrowser, ImageBrowserError


class AsyncRuntime:
    """Run an asynchronous Petey operation from a local Flask request."""

    def call(self, coroutine, timeout=660):
        async def run_with_cleanup():
            try:
                return await asyncio.wait_for(coroutine, timeout=timeout)
            finally:
                # A fresh event loop is used for each Flask worker request, so an
                # aiohttp session must not leak into the next request's loop.
                from petey.deapi_client import deapi

                await deapi.close()

        return asyncio.run(run_with_cleanup())

    def close(self):
        return None


def create_desktop_app(
    state: DesktopState | None = None,
    runtime: AsyncRuntime | None = None,
    gallery: MediaGallery | None = None,
    job_manager: MediaJobManager | None = None,
    memory: DesktopMemory | None = None,
    workspace_service: WorkspaceService | None = None,
) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
    app.config["PETEY_STATE"] = state or DesktopState()
    app.config["PETEY_RUNTIME"] = runtime or AsyncRuntime()
    app.config["PETEY_GALLERY"] = gallery or MediaGallery(
        app.config["PETEY_STATE"].data_dir / "gallery"
    )
    app.config["PETEY_MEDIA_JOBS"] = job_manager
    app.config["PETEY_WORKSPACES"] = workspace_service or WorkspaceService(
        app.config["PETEY_STATE"]
    )
    app.config["PETEY_IMAGE_BROWSER"] = ImageBrowser()

    def create_embedding(text: str):
        current: DesktopState = app.config["PETEY_STATE"]
        settings = current.memory_provider
        if not settings.get("semantic_enabled", True):
            return None
        provider = str(settings.get("provider") or "gemini")
        model = str(settings.get("models", {}).get(provider) or "")
        return AIProvider(current.ai_provider).embed(
            text, provider, model, str(settings.get("local_base_url") or "")
        )

    app.config["PETEY_MEMORY"] = memory or DesktopMemory(
        app.config["PETEY_STATE"].data_dir / "petey-memory-v2.sqlite3",
        create_embedding,
    )

    def get_media_jobs() -> MediaJobManager:
        manager = app.config.get("PETEY_MEDIA_JOBS")
        if manager is None:
            manager = MediaJobManager(app.config["PETEY_GALLERY"], max_workers=3)
            app.config["PETEY_MEDIA_JOBS"] = manager
        return manager

    def gallery_json(item: dict) -> dict:
        local = bool(item.get("local_filename"))
        return {
            **item,
            "media_url": (
                url_for("desktop_gallery_file", item_id=item["id"]) if local
                else item.get("remote_url", "")
            ),
        }

    app.config["PETEY_MEMORY"].init_db()

    @app.get("/")
    def desktop_home():
        return render_template("desktop.html")

    @app.get("/api/desktop/bootstrap")
    def desktop_bootstrap():
        current: DesktopState = app.config["PETEY_STATE"]
        return jsonify(
            {
                "name": "Petey",
                "person_name": current.display_name,
                "conversation_id": current.conversation_id,
                "conversations": current.conversations,
                "preferences": current.preferences,
                "installation_id": current.installation_id,
                "workspaces": current.workspaces,
                "active_workspace_id": current.active_workspace_id,
            }
        )

    @app.route("/api/desktop/workspaces", methods=["GET", "POST"])
    def desktop_workspaces():
        current: DesktopState = app.config["PETEY_STATE"]
        if request.method == "GET":
            return jsonify(
                {"workspaces": current.workspaces, "active_workspace_id": current.active_workspace_id}
            )
        payload = request.get_json(silent=True) or {}
        try:
            workspace = current.add_workspace(payload.get("path", ""))
            return jsonify(
                {"workspace": workspace, "workspaces": current.workspaces,
                 "active_workspace_id": current.active_workspace_id}
            ), 201
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.put("/api/desktop/workspaces/<workspace_id>/select")
    def desktop_select_workspace(workspace_id):
        current: DesktopState = app.config["PETEY_STATE"]
        try:
            return jsonify({"workspace": current.select_workspace(workspace_id)})
        except KeyError as exc:
            return jsonify({"error": str(exc).strip("'")}), 404

    @app.delete("/api/desktop/workspaces/<workspace_id>")
    def desktop_remove_workspace(workspace_id):
        current: DesktopState = app.config["PETEY_STATE"]
        try:
            removed = current.remove_workspace(workspace_id)
            return jsonify(
                {"removed": removed, "workspaces": current.workspaces,
                 "active_workspace_id": current.active_workspace_id}
            )
        except KeyError as exc:
            return jsonify({"error": str(exc).strip("'")}), 404

    @app.get("/api/desktop/workspace/tree")
    def desktop_workspace_tree():
        try:
            return jsonify(app.config["PETEY_WORKSPACES"].list_directory(
                request.args.get("workspace_id", ""), request.args.get("path", "")
            ))
        except WorkspaceError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.get("/api/desktop/workspace/file")
    def desktop_workspace_file():
        try:
            return jsonify(app.config["PETEY_WORKSPACES"].read_file(
                request.args.get("workspace_id", ""), request.args.get("path", "")
            ))
        except WorkspaceError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.put("/api/desktop/workspace/file")
    def desktop_save_workspace_file():
        payload = request.get_json(silent=True) or {}
        try:
            result = app.config["PETEY_WORKSPACES"].write_file(
                payload.get("workspace_id", ""), payload.get("path", ""),
                str(payload.get("content", "")), payload.get("expected_sha256"),
            )
            return jsonify({"file": result})
        except WorkspaceError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/desktop/workspace/command")
    def desktop_propose_workspace_command():
        payload = request.get_json(silent=True) or {}
        try:
            proposal = app.config["PETEY_WORKSPACES"].propose_command(
                payload.get("workspace_id", ""), payload.get("command", ""), payload.get("cwd", "")
            )
            return jsonify({"proposal": proposal}), 201
        except WorkspaceError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/desktop/workspace/agent")
    def desktop_workspace_agent():
        payload = request.get_json(silent=True) or {}
        try:
            return jsonify(app.config["PETEY_WORKSPACES"].agent_proposals(
                payload.get("workspace_id", ""), payload.get("instruction", ""),
                payload.get("selected_path", ""),
            ))
        except WorkspaceError as exc:
            return jsonify({"error": str(exc)}), 400
        except AIProviderError as exc:
            return jsonify({"error": str(exc)}), 502

    @app.post("/api/desktop/workspace/proposals/<proposal_id>/approve")
    def desktop_approve_workspace_proposal(proposal_id):
        try:
            return jsonify(app.config["PETEY_WORKSPACES"].approve(proposal_id))
        except WorkspaceError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.delete("/api/desktop/workspace/proposals/<proposal_id>")
    def desktop_reject_workspace_proposal(proposal_id):
        try:
            app.config["PETEY_WORKSPACES"].reject(proposal_id)
            return jsonify({"status": "rejected"})
        except WorkspaceError as exc:
            return jsonify({"error": str(exc)}), 404

    @app.get("/api/desktop/messages")
    def desktop_messages():
        current: DesktopState = app.config["PETEY_STATE"]
        messages = app.config["PETEY_MEMORY"].get_conversation_messages(
            current.installation_id, current.conversation_id, 100
        )
        return jsonify(
            [
                {
                    **item,
                    "role": "assistant" if item["user_id"] == PETEY_USER_ID else "user",
                }
                for item in messages
            ]
        )

    @app.post("/api/desktop/image-browser/open")
    def desktop_open_image_browser():
        payload = request.get_json(silent=True) or {}
        try:
            return jsonify(app.config["PETEY_IMAGE_BROWSER"].open(payload.get("path", ""))), 201
        except ImageBrowserError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.get("/api/desktop/image-browser/list")
    def desktop_list_images():
        try:
            return jsonify(app.config["PETEY_IMAGE_BROWSER"].list_directory(
                request.args.get("token", ""), request.args.get("path", "")
            ))
        except ImageBrowserError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.get("/api/desktop/image-browser/thumbnail")
    def desktop_image_thumbnail():
        try:
            thumbnail = app.config["PETEY_IMAGE_BROWSER"].thumbnail(
                request.args.get("token", ""), request.args.get("path", "")
            )
            return send_file(thumbnail, mimetype="image/jpeg", max_age=300)
        except ImageBrowserError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.get("/api/desktop/image-browser/file")
    def desktop_image_browser_file():
        try:
            path = app.config["PETEY_IMAGE_BROWSER"].image_file(
                request.args.get("token", ""), request.args.get("path", "")
            )
            return send_file(path, as_attachment=False, download_name=path.name)
        except ImageBrowserError as exc:
            return jsonify({"error": str(exc)}), 400
    @app.post("/api/desktop/chat")
    def desktop_chat():
        current: DesktopState = app.config["PETEY_STATE"]
        message = request.form.get("message", "")
        uploaded = request.files.get("attachment")
        attachment = None
        if uploaded and uploaded.filename:
            attachment = AssistantAttachment(
                filename=uploaded.filename,
                content_type=uploaded.mimetype or "application/octet-stream",
                data=uploaded.read(),
            )

        identity = AssistantIdentity(
            installation_id=current.installation_id,
            conversation_id=current.conversation_id,
            person_id=current.person_id,
            display_name=current.display_name,
        )
        service = AssistantService(
            current.system_prompt, current.ai_provider, app.config["PETEY_MEMORY"]
        )
        temporary = request.form.get("temporary", "").lower() in {"1", "true", "yes"}
        temporary_history = []
        if temporary:
            try:
                temporary_history = json.loads(request.form.get("temporary_history", "[]"))
                if not isinstance(temporary_history, list):
                    raise ValueError
            except (json.JSONDecodeError, ValueError):
                return jsonify({"error": "Temporary chat history is invalid."}), 400
        try:
            reply = app.config["PETEY_RUNTIME"].call(
                service.respond(
                    message,
                    identity,
                    attachment,
                    temporary=temporary,
                    temporary_history=temporary_history,
                )
            )
            return jsonify({"text": reply.text, "gif_url": reply.gif_url})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except AIProviderError as exc:
            return jsonify({"error": str(exc)}), 502
        except Exception as exc:
            print(f"[DESKTOP] Chat failed: {exc}")
            return jsonify({"error": "Petey had trouble processing that message."}), 500

    @app.route("/api/desktop/conversations", methods=["GET", "POST"])
    def desktop_conversations():
        current: DesktopState = app.config["PETEY_STATE"]
        if request.method == "POST":
            payload = request.get_json(silent=True) or {}
            conversation = current.create_conversation(payload.get("title", "New chat"))
            return jsonify(
                {
                    "conversation": conversation,
                    "conversation_id": current.conversation_id,
                    "conversations": current.conversations,
                }
            ), 201
        return jsonify(
            {
                "conversation_id": current.conversation_id,
                "conversations": current.conversations,
            }
        )

    @app.put("/api/desktop/conversations/<conversation_id>/select")
    def desktop_select_conversation(conversation_id):
        current: DesktopState = app.config["PETEY_STATE"]
        try:
            conversation = current.select_conversation(conversation_id)
            return jsonify({"conversation": conversation, "conversation_id": current.conversation_id})
        except KeyError as exc:
            return jsonify({"error": str(exc).strip("'")}), 404

    @app.delete("/api/desktop/conversations/<conversation_id>")
    def desktop_delete_conversation(conversation_id):
        current: DesktopState = app.config["PETEY_STATE"]
        try:
            deleted, active_id = current.delete_conversation(conversation_id)
        except KeyError as exc:
            return jsonify({"error": str(exc).strip("'")}), 404
        removed_messages = app.config["PETEY_MEMORY"].clear_conversation(
            current.installation_id, conversation_id
        )
        return jsonify(
            {
                "deleted": deleted,
                "deleted_messages": removed_messages,
                "conversation_id": active_id,
                "conversations": current.conversations,
            }
        )

    @app.route("/api/desktop/preferences", methods=["GET", "PUT"])
    def desktop_preferences():
        current: DesktopState = app.config["PETEY_STATE"]
        if request.method == "GET":
            return jsonify({"preferences": current.preferences})
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return jsonify({"error": "Preferences must be an object."}), 400
        try:
            return jsonify({"preferences": current.update_preferences(payload)})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.route("/api/desktop/ai-provider", methods=["GET", "PUT"])
    def desktop_ai_provider():
        current: DesktopState = app.config["PETEY_STATE"]
        if request.method == "GET":
            return jsonify({"configuration": AIProvider(current.ai_provider).public_config()})
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return jsonify({"error": "AI provider settings must be an object."}), 400
        try:
            current.update_ai_provider(payload)
            return jsonify({"configuration": AIProvider(current.ai_provider).public_config()})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/desktop/ai-provider/test")
    def desktop_test_ai_provider():
        current: DesktopState = app.config["PETEY_STATE"]
        provider = AIProvider(current.ai_provider)
        try:
            text = provider.complete(
                "Reply with exactly: Connection successful.",
                "You are testing an AI provider connection. Follow the instruction exactly.",
                [],
            )
            return jsonify({"status": "connected", "response": text, "configuration": provider.public_config()})
        except (AIProviderError, OSError) as exc:
            return jsonify({"error": str(exc)}), 502

    @app.get("/api/desktop/ai-provider/models")
    def desktop_ai_models():
        current: DesktopState = app.config["PETEY_STATE"]
        try:
            return jsonify({"models": AIProvider(current.ai_provider).list_models()})
        except AIProviderError as exc:
            return jsonify({"error": str(exc)}), 502

    @app.route("/api/desktop/personality", methods=["GET", "PUT"])
    def desktop_personality():
        current: DesktopState = app.config["PETEY_STATE"]
        if request.method == "GET":
            return jsonify({"persona": current.persona, "presets": PERSONA_PRESETS})
        try:
            changes = request.get_json(silent=True) or {}
            if not isinstance(changes, dict):
                return jsonify({"error": "Personality settings must be an object."}), 400
            persona = current.update_persona(changes)
            return jsonify({"status": "saved", "persona": persona})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/desktop/personality/rewrite")
    def desktop_personality_rewrite():
        current: DesktopState = app.config["PETEY_STATE"]
        prompt = (request.get_json(silent=True) or {}).get("prompt", "").strip()
        if not prompt:
            return jsonify({"error": "Enter a personality prompt first."}), 400
        system_message = (
            "You are an expert prompt engineer. Rewrite the user's rough chatbot identity "
            "as a detailed and effective system prompt beginning with 'You are'. Preserve "
            "their intent. Return only the final prompt with no quotes or markdown."
        )
        try:
            enhanced = AIProvider(current.ai_provider).complete(prompt, system_message, [])
            return jsonify({"prompt": enhanced.strip()})
        except AIProviderError as exc:
            return jsonify({"error": str(exc)}), 502

    @app.route("/api/desktop/knowledge", methods=["GET", "POST"])
    def desktop_knowledge():
        current: DesktopState = app.config["PETEY_STATE"]
        if request.method == "GET":
            return jsonify({"documents": app.config["PETEY_MEMORY"].get_documents(current.installation_id)})

        uploaded = request.files.get("file")
        if not uploaded or not uploaded.filename:
            return jsonify({"error": "Choose a file to upload."}), 400
        filename = PurePath(uploaded.filename.replace("\\", "/")).name
        extension = PurePath(filename).suffix.lower()
        if extension not in {".txt", ".md", ".json", ".pdf"}:
            return jsonify({"error": "Only .txt, .md, .json, and .pdf files are supported."}), 400

        try:
            if extension == ".pdf":
                try:
                    import PyPDF2
                except ImportError:
                    return jsonify({"error": "PDF support requires PyPDF2."}), 500
                reader = PyPDF2.PdfReader(uploaded.stream)
                text = "\n".join(page.extract_text() or "" for page in reader.pages)
            else:
                text = uploaded.read().decode("utf-8", errors="ignore")
            if not text.strip():
                return jsonify({"error": "No readable text was found in that file."}), 400
            # Re-uploading a filename replaces its old chunks instead of silently
            # doubling its influence in semantic retrieval.
            app.config["PETEY_MEMORY"].delete_document(current.installation_id, filename)
            app.config["PETEY_MEMORY"].store_document(current.installation_id, filename, text)
            return jsonify(
                {
                    "status": "queued",
                    "filename": filename,
                    "message": f"{filename} is being added to Petey's knowledge.",
                }
            ), 202
        except Exception as exc:
            return jsonify({"error": f"Could not read the file: {exc}"}), 400

    @app.delete("/api/desktop/knowledge/<path:filename>")
    def desktop_delete_knowledge(filename):
        current: DesktopState = app.config["PETEY_STATE"]
        safe_name = PurePath(filename.replace("\\", "/")).name
        if not app.config["PETEY_MEMORY"].delete_document(current.installation_id, safe_name):
            return jsonify({"error": "The document could not be deleted."}), 500
        return jsonify({"status": "deleted", "filename": safe_name})

    @app.post("/api/desktop/knowledge/search")
    def desktop_search_knowledge():
        current: DesktopState = app.config["PETEY_STATE"]
        query = (request.get_json(silent=True) or {}).get("query", "").strip()
        if not query:
            return jsonify({"error": "Enter something to search for."}), 400
        result = app.config["PETEY_MEMORY"].search_memories(query, current.installation_id, 8)
        return jsonify({"query": query, "result": result, "found": bool(result.strip())})

    @app.get("/api/desktop/memory/stats")
    def desktop_memory_stats():
        current: DesktopState = app.config["PETEY_STATE"]
        return jsonify(
            app.config["PETEY_MEMORY"].get_memory_stats(
                current.installation_id, current.conversation_id
            )
        )

    @app.route("/api/desktop/memory/provider", methods=["GET", "PUT"])
    def desktop_memory_provider():
        current: DesktopState = app.config["PETEY_STATE"]
        if request.method == "PUT":
            payload = request.get_json(silent=True) or {}
            if not isinstance(payload, dict):
                return jsonify({"error": "Memory provider settings must be an object."}), 400
            try:
                current.update_memory_provider(payload)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
        settings = current.memory_provider
        provider = settings.get("provider", "gemini")
        return jsonify(
            {
                "configuration": {
                    **settings,
                    "model": settings.get("models", {}).get(provider, ""),
                    "database": "local SQLite",
                }
            }
        )

    @app.post("/api/desktop/memory/provider/test")
    def desktop_test_memory_provider():
        current: DesktopState = app.config["PETEY_STATE"]
        settings = current.memory_provider
        if not settings.get("semantic_enabled", True):
            return jsonify({"status": "disabled", "message": "Semantic memory is disabled."})
        provider = str(settings.get("provider") or "gemini")
        model = str(settings.get("models", {}).get(provider) or "")
        try:
            result = AIProvider(current.ai_provider).embed(
                "Petey universal memory connection test",
                provider,
                model,
                str(settings.get("local_base_url") or ""),
            )
            return jsonify(
                {
                    "status": "connected",
                    "provider": result["provider"],
                    "model": result["model"],
                    "dimensions": result["dimensions"],
                }
            )
        except AIProviderError as exc:
            return jsonify({"error": str(exc)}), 502

    @app.post("/api/desktop/memory/rebuild")
    def desktop_rebuild_memory():
        current: DesktopState = app.config["PETEY_STATE"]
        count = app.config["PETEY_MEMORY"].rebuild_embeddings(current.installation_id)
        return jsonify({"status": "queued", "items": count}), 202

    @app.delete("/api/desktop/memory/all")
    def desktop_reset_memory():
        current: DesktopState = app.config["PETEY_STATE"]
        deleted = app.config["PETEY_MEMORY"].reset(current.installation_id)
        return jsonify({"status": "reset", "deleted": deleted})

    @app.delete("/api/desktop/memory/conversation")
    def desktop_clear_conversation():
        current: DesktopState = app.config["PETEY_STATE"]
        deleted = app.config["PETEY_MEMORY"].clear_conversation(
            current.installation_id, current.conversation_id
        )
        return jsonify({"status": "cleared", "deleted": deleted})

    @app.get("/api/desktop/media")
    def desktop_media_catalog():
        current: DesktopState = app.config["PETEY_STATE"]
        operations = MediaService.operation_catalog()
        service = MediaService()
        return jsonify(
            {
                "operations": operations,
                "configured": bool(service.client.api_key),
                "selected_models": {
                    operation: current.selected_model(operation) for operation in operations
                },
            }
        )

    @app.get("/api/desktop/media/models/<operation>")
    def desktop_media_models(operation):
        try:
            models = app.config["PETEY_RUNTIME"].call(
                MediaService().models(operation), timeout=90
            )
            return jsonify({"operation": operation, "models": models})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": f"Could not load deAPI models: {exc}"}), 502

    @app.get("/api/desktop/media/balance")
    def desktop_media_balance():
        try:
            balance = app.config["PETEY_RUNTIME"].call(
                MediaService().balance(), timeout=30
            )
            return jsonify({"balance": balance, "currency": "USD"})
        except Exception as exc:
            return jsonify({"error": f"Could not load deAPI balance: {exc}"}), 502

    @app.post("/api/desktop/media/enhance")
    def desktop_media_enhance():
        current: DesktopState = app.config["PETEY_STATE"]
        payload = request.get_json(silent=True) or {}
        prompt = str(payload.get("prompt") or "").strip()
        operation = str(payload.get("operation") or "txt2img")
        if not prompt:
            return jsonify({"error": "Enter a prompt first."}), 400
        if operation not in MediaService.operation_catalog():
            return jsonify({"error": "Unsupported media operation."}), 400
        system_message = (
            "Rewrite the user's idea as a vivid, precise prompt for an AI media generator. "
            "Preserve their subject and intent, add useful style, composition, lighting, mood, "
            "and motion details where relevant. Return only the enhanced prompt under 500 characters."
        )
        try:
            enhanced = AIProvider(current.ai_provider).complete(prompt, system_message, [])
            return jsonify({"prompt": enhanced.strip()[:500]})
        except AIProviderError as exc:
            return jsonify({"error": str(exc)}), 502

    @app.post("/api/desktop/media/generate")
    def desktop_media_generate():
        current: DesktopState = app.config["PETEY_STATE"]
        operation = request.form.get("operation", "")
        prompt = request.form.get("prompt", "")
        model_slug = request.form.get("model_slug", "")
        try:
            parameters = json.loads(request.form.get("parameters", "{}"))
            if not isinstance(parameters, dict):
                raise ValueError
        except (json.JSONDecodeError, ValueError):
            return jsonify({"error": "Media parameters are invalid."}), 400

        uploaded = request.files.get("source")
        source = None
        if uploaded and uploaded.filename:
            source = MediaInput(
                filename=PurePath(uploaded.filename.replace("\\", "/")).name,
                content_type=uploaded.mimetype or "application/octet-stream",
                data=uploaded.read(),
            )
        try:
            job = get_media_jobs().submit(
                operation=operation,
                prompt=prompt,
                installation_id=current.installation_id,
                model_slug=model_slug,
                source=source,
                parameters=parameters,
            )
            current.update_selected_model(operation, model_slug)
            if job["kind"] == "image":
                app.config["PETEY_MEMORY"].record_image_generation(
                    current.installation_id, current.person_id, prompt
                )
            return jsonify({"status": "queued", "job": job}), 202
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            print(f"[DESKTOP] Could not queue deAPI generation: {exc}")
            return jsonify({"error": f"Could not queue generation: {exc}"}), 500

    @app.get("/api/desktop/media/jobs")
    def desktop_media_jobs():
        return jsonify({"jobs": get_media_jobs().list_jobs()})

    @app.get("/api/desktop/media/jobs/<job_id>")
    def desktop_media_job(job_id):
        job = get_media_jobs().get(job_id)
        if not job:
            return jsonify({"error": "Generation job not found."}), 404
        return jsonify({"job": job})

    @app.get("/api/desktop/gallery")
    def desktop_gallery():
        gallery_store: MediaGallery = app.config["PETEY_GALLERY"]
        return jsonify({"items": [gallery_json(item) for item in gallery_store.list_items()]})

    @app.get("/api/desktop/gallery/file/<item_id>")
    def desktop_gallery_file(item_id):
        gallery_store: MediaGallery = app.config["PETEY_GALLERY"]
        path = gallery_store.file_path(item_id)
        if path is None:
            return jsonify({"error": "Local gallery file not found."}), 404
        return send_file(
            path,
            as_attachment=request.args.get("download") == "1",
            download_name=path.name,
        )

    @app.delete("/api/desktop/gallery/<item_id>")
    def desktop_delete_gallery_item(item_id):
        gallery_store: MediaGallery = app.config["PETEY_GALLERY"]
        if not gallery_store.delete(item_id):
            return jsonify({"error": "Gallery item not found."}), 404
        return jsonify({"status": "deleted", "id": item_id})

    @app.errorhandler(413)
    def attachment_too_large(_error):
        return jsonify({"error": "Attachments must be 25 MB or smaller."}), 413

    return app
