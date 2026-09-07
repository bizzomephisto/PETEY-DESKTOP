import os
import aiohttp
import asyncio
import time
import io
import random
import math

from petey.deapi_tts import DEAPI_TTS_MODEL

class DeapiError(Exception):
    pass

class RateLimitError(DeapiError):
    pass

class DeapiClient:
    PRICE_ENDPOINTS = {
        "txt2img": "/api/v2/images/generations/price",
        "img2img": "/api/v2/images/edits/price",
        "txt2video": "/api/v2/videos/generations/price",
        "img2video": "/api/v2/videos/animations/price",
        "img-rmbg": "/api/v2/images/background-removals/price",
        "img-upscale": "/api/v2/images/upscales/price",
    }
    # deAPI currently omits MiniMax H3's fixed step count from its model metadata,
    # while both the v1 and v2 validators require exactly 8 steps.
    MODEL_PARAMETER_OVERRIDES = {
        "MiniMaxH3_33B_Turbo_INT8": {"steps": 8},
    }

    def __init__(self, progress_callback=None, api_key=None):
        self.api_key = api_key or os.getenv("DEAPI_KEY")
        if not self.api_key:
            print("[WARNING] DEAPI_KEY not found in environment variables. deAPI features will not work.")

        self.base_url = "https://api.deapi.ai"
        self._session = None
        self._cache = {}
        self._cache_ts = {}
        self.cache_ttl = 86400  # 24 hours
        self.progress_callback = progress_callback

    def _report_progress(self, request_id, data):
        if not self.progress_callback:
            return
        update = {
            "request_id": request_id,
            "status": str(data.get("status") or "processing"),
            "progress": data.get("progress"),
            "preview_url": data.get("preview") or data.get("preview_url") or "",
        }
        try:
            self.progress_callback(update)
        except Exception as exc:
            # UI reporting must never interrupt a paid generation.
            print(f"[DEAPI] Progress callback failed: {exc}")

    def _get_headers(self, content_type="application/json"):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json"
        }
        # Only set if explicitly provided, aiohttp handles multipart boundaries automatically
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or getattr(self._session, "closed", True):
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not getattr(self._session, "closed", True):
            await self._session.close()

    async def get_balance(self):
        """Return the authenticated account's current deAPI credit balance."""
        if not self.api_key:
            raise DeapiError("DEAPI_KEY is not configured.")
        session = await self.get_session()
        async with session.get(
            f"{self.base_url}/api/v2/account/balance",
            headers=self._get_headers(),
        ) as response:
            response.raise_for_status()
            payload = await response.json()
        balance = payload.get("data", {}).get("balance")
        if balance is None:
            raise DeapiError("deAPI returned a balance response without a balance value.")
        try:
            return float(balance)
        except (TypeError, ValueError) as exc:
            raise DeapiError("deAPI returned an invalid balance value.") from exc

    async def estimate_price(self, operation, model_slug, parameters, prompt="", source=None):
        """Read a provider quote; never submit or poll a generation job."""
        endpoint = self.PRICE_ENDPOINTS.get(operation)
        if not endpoint:
            raise ValueError("Price lookup is unavailable for this operation.")
        models = await self.get_models(operation)
        model = next((item for item in models if item.get("slug") == model_slug), None) if model_slug else next(iter(models), None)
        if not model:
            raise ValueError("Choose an available model to estimate its price.")
        slug = model["slug"]
        info = model.get("info") or {}
        defaults = info.get("defaults") or {}
        payload = {"model": slug}
        effective = {}
        if operation in {"txt2img", "img2img"}:
            effective = self._image_parameters(defaults, info, {**parameters, "seed": 0})
            payload.update(effective)
            payload["prompt"] = prompt.strip() or "Image"
        elif operation in {"txt2video", "img2video"}:
            effective = self._video_parameters(slug, defaults, info, {**parameters, "seed": 0})
            payload.update({name: effective[name] for name in ("width", "height", "steps", "frames", "fps")})
        else:
            if source is None:
                raise ValueError("Choose a source image to estimate its price.")
            payload = aiohttp.FormData()
            payload.add_field("model", slug)
            if operation == "img-upscale":
                payload.add_field("scale", str(parameters["scale"]))
            payload.add_field("image", source.data, filename=source.filename, content_type=source.content_type)
        session = await self.get_session()
        multipart = isinstance(payload, aiohttp.FormData)
        async with session.post(
            f"{self.base_url}{endpoint}",
            headers=self._get_headers(None if multipart else "application/json"),
            timeout=aiohttp.ClientTimeout(total=20),
            **({"data": payload} if multipart else {"json": payload}),
        ) as response:
            response.raise_for_status()
            body = await response.json()
        try:
            data = body["data"]
            raw_price = data["price"]
            price = float(raw_price)
            if isinstance(raw_price, bool) or not math.isfinite(price) or price < 0:
                raise ValueError
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise DeapiError("The media provider returned an invalid price estimate.") from exc
        return {"price": price, "currency": "USD", "is_estimated": bool(data.get("is_estimated", True)),
                "model_slug": slug, "parameters": {key: value for key, value in effective.items() if key != "seed"}}

    async def get_models(self, inference_type=None, force_refresh=False):
        if not self.api_key:
            raise DeapiError("DEAPI_KEY is not configured in the project .env file.")
        cache_key = inference_type or "__all__"
        import time
        now = time.time()

        if (not force_refresh
            and cache_key in self._cache
            and now - self._cache_ts.get(cache_key, 0.0) < self.cache_ttl):
            return self._cache[cache_key]

        session = await self.get_session()
        params = {}
        if inference_type:
            params["filter[inference_types]"] = inference_type

        try:
            models = []
            page = 1
            while True:
                page_params = {**params, "page": page}
                async with session.get(
                    f"{self.base_url}/api/v2/models",
                    headers=self._get_headers(),
                    params=page_params,
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    models.extend(data.get("data", []))

                meta = data.get("meta", {})
                current_page = int(meta.get("current_page", page))
                last_page = int(meta.get("last_page", current_page))
                if current_page >= last_page:
                    break
                page = current_page + 1

            self._cache[cache_key] = models
            self._cache_ts[cache_key] = now
            return models
        except (aiohttp.ClientResponseError, ValueError, TypeError) as e:
            if isinstance(e, aiohttp.ClientResponseError):
                print(f"[ERROR] Failed to fetch models: {e.status}")
            else:
                print(f"[ERROR] Invalid model catalog response: {e}")
            return []

    async def _execute_with_fallback(
        self, endpoint, payload_builder, inference_type, is_multipart=False,
        guild_id=None, selected_model_slug=None, strict_model=False,
    ):
        """Try available models until one succeeds."""
        models = await self.get_models(inference_type)
        if not models:
            raise DeapiError(f"No models found for inference type: {inference_type}")

        if selected_model_slug:
            filtered = [m for m in models if m["slug"] == selected_model_slug]
            if filtered:
                models = filtered
            elif strict_model:
                raise DeapiError(f"Selected model {selected_model_slug} is unavailable.")
            else:
                print(f"[WARNING] Selected model {selected_model_slug} not found. Falling back to defaults.")

        session = await self.get_session()
        last_error = None

        for model in models:
            model_slug = model["slug"]
            info = model.get("info", {})
            defaults = info.get("defaults", {})
            try:
                # Build payload specific to this model
                payload = payload_builder(model_slug, defaults, info)

                headers = self._get_headers(None if is_multipart else "application/json")

                if is_multipart:
                    async with session.post(f"{self.base_url}{endpoint}", headers=headers, data=payload) as resp:
                         if resp.status == 429:
                              retry_after = int(resp.headers.get("Retry-After", 5))
                              await asyncio.sleep(retry_after)
                              continue
                         if resp.status >= 400:
                              err_text = await resp.text()
                              print(f"[ERROR {resp.status}] {endpoint} Model {model_slug}: {err_text}")
                              raise DeapiError(f"Server rejected request: {err_text}")
                         result = await resp.json()
                         return result.get("data", {}).get("request_id")
                else:
                    async with session.post(f"{self.base_url}{endpoint}", headers=headers, json=payload) as resp:
                         if resp.status == 429:
                              retry_after = int(resp.headers.get("Retry-After", 5))
                              await asyncio.sleep(retry_after)
                              continue
                         if resp.status >= 400:
                              err_text = await resp.text()
                              print(f"[ERROR {resp.status}] {endpoint} Model {model_slug}: {err_text}")
                              raise DeapiError(f"Server rejected request: {err_text}")
                         result = await resp.json()
                         return result.get("data", {}).get("request_id")

            except aiohttp.ClientResponseError as e:
                print(f"[DEBUG] Model {model_slug} failed with status {e.status}")
                last_error = e
                continue
            except Exception as e:
                print(f"[DEBUG] Model {model_slug} failed: {e}")
                last_error = e
                continue

        if last_error:
            raise last_error
        raise DeapiError("All models failed")

    @staticmethod
    def _bounded_model_value(name, kwargs, defaults, limits, fallback):
        """Resolve a model parameter and keep it within advertised limits."""
        value = kwargs.get(name, defaults.get(name, fallback))
        minimum = limits.get(f"min_{name}")
        maximum = limits.get(f"max_{name}")
        if minimum is not None:
            value = max(value, minimum)
        if maximum is not None:
            value = min(value, maximum)
        return value

    def _video_parameters(self, model, defaults, info, kwargs):
        """Build parameters valid for the selected video model's contract."""
        limits = info.get("limits", {})
        features = info.get("features", {})
        overrides = self.MODEL_PARAMETER_OVERRIDES.get(model, {})

        params = {
            "width": self._bounded_model_value("width", kwargs, defaults, limits, 512),
            "height": self._bounded_model_value("height", kwargs, defaults, limits, 512),
            "steps": self._bounded_model_value(
                "steps", kwargs, defaults, limits, overrides.get("steps", 20)
            ),
            "frames": self._bounded_model_value("frames", kwargs, defaults, limits, 120),
            "fps": self._bounded_model_value("fps", kwargs, defaults, limits, 24),
            "seed": kwargs.get("seed", random.randint(0, 2**32 - 1)),
        }

        if features.get("supports_guidance") or "guidance" in kwargs:
            params["guidance"] = kwargs.get("guidance", defaults.get("guidance", 3.5))
        if features.get("supports_negative_prompt"):
            params["negative_prompt"] = kwargs.get(
                "negative_prompt", defaults.get("negative_prompt", "")
            )
        return params

    def _image_parameters(self, defaults, info, kwargs):
        limits = info.get("limits", {})
        return {
            "width": self._bounded_model_value("width", kwargs, defaults, limits, 1024),
            "height": self._bounded_model_value("height", kwargs, defaults, limits, 1024),
            "steps": self._bounded_model_value("steps", kwargs, defaults, limits, 20),
            "guidance": kwargs.get("guidance", defaults.get("guidance", 3.5)),
            "seed": kwargs.get("seed", random.randint(0, 2**32 - 1)),
        }

    async def wait_for_job(self, request_id, interval=2, timeout=300):
        url = f"{self.base_url}/api/v1/client/request-status/{request_id}"
        session = await self.get_session()
        start = time.time()

        while time.time() - start < timeout:
            async with session.get(url, headers=self._get_headers()) as resp:
                resp.raise_for_status()
                json_resp = await resp.json()
                data = json_resp.get("data", {})

                status = data.get("status")
                self._report_progress(request_id, data)
                if status == "done":
                    return data
                if status == "error":
                    raise DeapiError(f"Job {request_id} failed: {data}")

                try:
                    progress = float(data.get("progress") or 0)
                except (TypeError, ValueError):
                    progress = 0
                if progress > 50:
                    await asyncio.sleep(interval)
                else:
                    await asyncio.sleep(interval * 2)

        raise TimeoutError(f"Job {request_id} timed out after {timeout}s")

    async def wait_for_v2_job(self, request_id, interval=1.25, timeout=300):
        """Poll a v2 job without exceeding the documented 50 RPM status limit."""
        url = f"{self.base_url}/api/v2/jobs/{request_id}"
        session = await self.get_session()
        start = time.time()

        while time.time() - start < timeout:
            async with session.get(url, headers=self._get_headers()) as resp:
                resp.raise_for_status()
                json_resp = await resp.json()
                data = json_resp.get("data", {})
                status = str(data.get("status") or "").lower()
                self._report_progress(request_id, data)
                if status in {"done", "completed", "success"}:
                    return data
                if status in {"error", "failed", "cancelled"}:
                    raise DeapiError(f"Job {request_id} failed: {data}")
            await asyncio.sleep(interval)

        raise TimeoutError(f"Job {request_id} timed out after {timeout}s")

    def _get_bytes(self, url_or_bytes):
        return url_or_bytes

    async def generate_image(self, prompt, **kwargs):
        guild_id = kwargs.pop("guild_id", None)
        model_slug = kwargs.pop("model_slug", None)
        def build_payload(model, defaults, info):
            return {
                "prompt": prompt,
                "model": model,
                **self._image_parameters({"steps": 4, **defaults}, info, kwargs),
            }

        req_id = await self._execute_with_fallback("/api/v1/client/txt2img", build_payload, "txt2img", guild_id=guild_id, selected_model_slug=model_slug)
        return await self.wait_for_job(req_id)

    async def generate_image_to_image(self, prompt, image_bytes, **kwargs):
        guild_id = kwargs.pop("guild_id", None)
        model_slug = kwargs.pop("model_slug", None)
        def build_payload(model, defaults, info):
            data = aiohttp.FormData()
            data.add_field("prompt", prompt)
            data.add_field("model", model)
            for name, value in self._image_parameters(defaults, info, kwargs).items():
                data.add_field(name, str(value))
            data.add_field("image", io.BytesIO(image_bytes), filename="source.png", content_type="image/png")
            return data

        req_id = await self._execute_with_fallback("/api/v1/client/img2img", build_payload, "img2img", is_multipart=True, guild_id=guild_id, selected_model_slug=model_slug)
        return await self.wait_for_job(req_id, timeout=600)

    async def generate_video(self, prompt, **kwargs):
        guild_id = kwargs.pop("guild_id", None)
        model_slug = kwargs.pop("model_slug", None)
        def build_payload(model, defaults, info):
            return {
                "prompt": prompt,
                "model": model,
                **self._video_parameters(model, defaults, info, kwargs),
            }

        req_id = await self._execute_with_fallback("/api/v1/client/txt2video", build_payload, "txt2video", guild_id=guild_id, selected_model_slug=model_slug)
        return await self.wait_for_job(req_id, interval=5, timeout=900)  # Longer polling interval for video

    async def generate_image_to_video(self, prompt, image_bytes, **kwargs):
        guild_id = kwargs.pop("guild_id", None)
        model_slug = kwargs.pop("model_slug", None)
        def build_payload(model, defaults, info):
            video_params = self._video_parameters(model, defaults, info, kwargs)
            data = aiohttp.FormData()
            data.add_field("prompt", prompt)
            data.add_field("model", model)
            for name, value in video_params.items():
                data.add_field(name, str(value))
            data.add_field("first_frame_image", io.BytesIO(image_bytes), filename="start.png", content_type="image/png")
            return data

        req_id = await self._execute_with_fallback("/api/v1/client/img2video", build_payload, "img2video", is_multipart=True, guild_id=guild_id, selected_model_slug=model_slug)
        return await self.wait_for_job(req_id, interval=5, timeout=900)

    async def generate_video_to_video(self, prompt, video_bytes, **kwargs):
        guild_id = kwargs.pop("guild_id", None)
        model_slug = kwargs.pop("model_slug", None)
        def build_payload(model, defaults, info):
            data = aiohttp.FormData()
            data.add_field("prompt", prompt)
            data.add_field("model", model)
            data.add_field("steps", str(kwargs.get("steps", defaults.get("steps", 20))))
            data.add_field("seed", str(random.randint(0, 2**32 - 1)))
            data.add_field("guidance", str(kwargs.get("guidance", defaults.get("guidance", 3.5))))
            data.add_field("video", io.BytesIO(video_bytes), filename="source.mp4", content_type="video/mp4")
            return data

        req_id = await self._execute_with_fallback("/api/v1/client/vid2video", build_payload, "vid2video", is_multipart=True, guild_id=guild_id, selected_model_slug=model_slug)
        return await self.wait_for_job(req_id, interval=5, timeout=900)

    async def generate_remove_bg(self, image_bytes, **kwargs):
        guild_id = kwargs.pop("guild_id", None)
        model_slug = kwargs.pop("model_slug", None)
        def build_payload(model, defaults, info):
            data = aiohttp.FormData()
            data.add_field("model", model)
            data.add_field("image", io.BytesIO(image_bytes), filename="source.png", content_type="image/png")
            return data

        req_id = await self._execute_with_fallback("/api/v1/client/img-rmbg", build_payload, "img-rmbg", is_multipart=True, guild_id=guild_id, selected_model_slug=model_slug)
        return await self.wait_for_job(req_id)

    async def generate_upscale(self, image_bytes, scale=2, **kwargs):
        guild_id = kwargs.pop("guild_id", None)
        model_slug = kwargs.pop("model_slug", None)
        def build_payload(model, defaults, info):
            data = aiohttp.FormData()
            data.add_field("model", model)
            data.add_field("scale", str(scale))
            data.add_field("image", io.BytesIO(image_bytes), filename="source.png", content_type="image/png")
            return data

        req_id = await self._execute_with_fallback("/api/v1/client/img-upscale", build_payload, "img-upscale", is_multipart=True, guild_id=guild_id, selected_model_slug=model_slug)
        return await self.wait_for_job(req_id, timeout=600)

    async def generate_music(self, caption, **kwargs):
        guild_id = kwargs.pop("guild_id", None)
        model_slug = kwargs.pop("model_slug", None)
        def build_payload(model, defaults, info):
            data = aiohttp.FormData()
            data.add_field("caption", caption)
            data.add_field("model", model)
            # Default to no vocals mode if no lyrics
            data.add_field("lyrics", kwargs.get("lyrics", "[Instrumental]"))
            data.add_field("duration", str(kwargs.get("duration", 30)))
            data.add_field("inference_steps", str(kwargs.get("inference_steps", 8)))
            data.add_field("guidance_scale", str(kwargs.get("guidance_scale", 1)))
            data.add_field("seed", "-1")
            data.add_field("format", "mp3")

            ref_audio = kwargs.get("reference_audio")
            if ref_audio:
                data.add_field("reference_audio", io.BytesIO(ref_audio), filename="ref.mp3", content_type="audio/mpeg")

            return data

        req_id = await self._execute_with_fallback("/api/v1/client/txt2music", build_payload, "txt2music", is_multipart=True, guild_id=guild_id, selected_model_slug=model_slug)
        return await self.wait_for_job(req_id, interval=4)

    async def generate_speech(self, text, **kwargs):
        guild_id = kwargs.pop("guild_id", None)
        model_slug = kwargs.pop("model_slug", None) or DEAPI_TTS_MODEL
        def build_payload(model, defaults, info):
            data = aiohttp.FormData()
            data.add_field("text", text)
            data.add_field("model", model)
            data.add_field("lang", kwargs.get("lang", "English"))
            data.add_field("speed", str(kwargs.get("speed", 1)))
            data.add_field("format", "mp3")
            data.add_field("sample_rate", "24000")
            data.add_field("mode", kwargs.get("mode", "custom_voice"))
            data.add_field("voice", kwargs.get("voice", "Vivian"))
            if kwargs.get("style"):
                data.add_field("instruct", kwargs["style"])
            return data

        req_id = await self._execute_with_fallback(
            "/api/v2/audio/speech", build_payload, "txt2audio",
            is_multipart=True, guild_id=guild_id,
            selected_model_slug=model_slug, strict_model=True,
        )
        return await self.wait_for_v2_job(req_id)

    async def image_to_text(self, image_bytes, **kwargs):
        guild_id = kwargs.pop("guild_id", None)
        model_slug = kwargs.pop("model_slug", None)
        def build_payload(model, defaults, info):
            data = aiohttp.FormData()
            data.add_field("model", model)
            data.add_field("image", io.BytesIO(image_bytes), filename="source.png", content_type="image/png")
            return data

        req_id = await self._execute_with_fallback("/api/v1/client/img2txt", build_payload, "img2txt", is_multipart=True, guild_id=guild_id, selected_model_slug=model_slug)
        job_res = await self.wait_for_job(req_id)
        print(f"[IMAGE-TO-TEXT DEBUG] Raw deAPI response: {job_res}")
        if job_res:
            res_val = job_res.get("result")
            if not res_val and job_res.get("result_url"):
                try:
                    session = await self.get_session()
                    async with session.get(job_res.get("result_url")) as txt_resp:
                        if txt_resp.status == 200:
                            res_val = await txt_resp.text()
                            print(f"[IMAGE-TO-TEXT] Fetched content from result_url, length: {len(res_val)}")
                except Exception as fetch_err:
                    print(f"[IMAGE-TO-TEXT ERROR] Failed to fetch result_url: {fetch_err}")
            return res_val
        return None

# Global singleton instance for the bot
deapi = DeapiClient()
