"""Regression coverage for ordered, model-aware image editing (no paid calls)."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from petey.deapi_client import DeapiClient, DeapiError
from petey.deapi_image_models import image_model_info
from petey.desktop_state import DesktopState
from petey.media_service import MediaInput, MediaService
from web.desktop_app import AsyncRuntime
from web.desktop_app import create_desktop_app


class ImageEditingTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_prefers_saved_edit_model_only_if_it_fits_the_full_reference_set(self):
        client = DeapiClient(api_key='test')
        client.get_models = AsyncMock(return_value=[
            {'slug': 'QwenImageEdit_Plus_NF4'},
            {'slug': 'Flux_2_Klein_4B_BF16'},
            {'slug': 'gpt-image-2.5', 'info': {'limits': {'max_input_images': 4}}},
        ])
        self.assertEqual(await client.select_image_edit_model(2, 'QwenImageEdit_Plus_NF4'), 'Flux_2_Klein_4B_BF16')
        self.assertEqual(await client.select_image_edit_model(2, 'gpt-image-2.5'), 'gpt-image-2.5')
        with self.assertRaisesRegex(DeapiError, 'accepts 5 images'):
            await client.select_image_edit_model(5, 'gpt-image-2.5')

    async def test_ordered_uploads_and_model_fields_use_v2(self):
        client = DeapiClient(api_key='test')
        captured = {}
        async def execute(endpoint, builder, inference_type, **kwargs):
            captured.update(endpoint=endpoint, strict=kwargs['strict_model'])
            captured['fields'] = builder('gpt-image-2.5', {}, image_model_info('gpt-image-2.5'))._fields
            return 'job'
        client._execute_with_fallback = AsyncMock(side_effect=execute)
        client.wait_for_v2_job = AsyncMock(return_value={'result_url': 'https://example.com/edit.png'})
        images = [MediaInput('first.jpg', 'image/jpeg', b'first'), MediaInput('second.webp', 'image/webp', b'second')]
        await client.generate_image_to_image('Combine', references=images, quality='low', seed=123)
        self.assertEqual(captured['endpoint'], '/api/v2/images/edits')
        self.assertTrue(captured['strict'])
        fields = captured['fields']
        self.assertEqual([header['filename'] for header, _, _ in fields if header['name'] == 'images[]'], ['first.jpg', 'second.webp'])
        values = {header['name']: value for header, _, value in fields}
        self.assertEqual(values['quality'], 'low')
        self.assertEqual(values['seed'], '123')
        self.assertNotIn('image', values)
        self.assertNotIn('steps', values)
        self.assertNotIn('guidance', values)
        client.wait_for_v2_job.assert_awaited_once_with('job', timeout=600)

    async def test_live_reference_limit_rejects_before_submission(self):
        client = DeapiClient(api_key='test')
        async def execute(endpoint, builder, inference_type, **kwargs):
            builder('Flux_2_Klein_4B_BF16', {}, {'limits': {'max_input_images': 2}})
        client._execute_with_fallback = AsyncMock(side_effect=execute)
        with self.assertRaisesRegex(ValueError, 'at most 2'):
            await client.generate_image_to_image('Combine', references=[MediaInput('a.png', 'image/png', b'x')] * 3)

    def test_contract_fields_and_live_metadata_override(self):
        client = DeapiClient(api_key='test')
        qwen = image_model_info('QwenImageEdit_Plus_NF4')
        params = client._image_parameters({}, qwen, {'negative_prompt': 'blur', 'seed': 0}, editing=True)
        self.assertEqual(params, {'steps': 40, 'negative_prompt': 'blur', 'seed': 0})
        info = image_model_info('gpt-image-2', {'limits': {'quality_options': ['high'], 'max_input_images': 4}, 'features': {'supports_steps': True}})
        self.assertEqual(info['limits']['max_input_images'], 4)
        self.assertTrue(info['features']['supports_steps'])
        with self.assertRaisesRegex(ValueError, 'quality'):
            client._image_parameters({}, info, {'quality': 'low'})

    def test_grid_pixel_budget_and_ratio(self):
        client = DeapiClient(api_key='test')
        info = {'limits': {'resolution_step': 16, 'max_pixels': 1000000, 'max_ratio': 3}}
        params = client._image_parameters({}, info, {'width': 777, 'height': 513})
        self.assertEqual((params['width'], params['height']), (768, 512))
        with self.assertRaisesRegex(ValueError, 'pixel limit'):
            client._image_parameters({}, info, {'width': 1536, 'height': 1536})
        with self.assertRaisesRegex(ValueError, 'aspect ratio'):
            client._image_parameters({}, info, {'width': 2048, 'height': 256})

    async def test_dispatches_references_and_preserves_partner_size(self):
        client = AsyncMock()
        client.generate_image_to_image.return_value = {'result_url': 'https://example.com/edit.png'}
        images = [MediaInput('a.png', 'image/png', b'a'), MediaInput('b.jpg', 'image/jpeg', b'b')]
        await MediaService(client).generate('img2img', 'Combine', 'test', 'gpt-image-2.5', references=images, parameters={'width': 3840, 'height': 1024, 'quality': 'high', 'seed': 0})
        call = client.generate_image_to_image.await_args
        self.assertEqual(call.kwargs['references'], images)
        self.assertEqual(call.kwargs['width'], 3840)
        self.assertEqual(call.kwargs['quality'], 'high')
        self.assertNotIn('steps', call.kwargs)
        with self.assertRaisesRegex(ValueError, 'must be an image'):
            await MediaService(client).generate('img2img', 'Combine', 'test', references=[MediaInput('a.mp4', 'video/mp4', b'x')])


class ImageEditRouteTests(unittest.TestCase):
    def test_mixed_browser_and_upload_references_keep_user_order(self):
        with tempfile.TemporaryDirectory() as folder:
            images = Path(folder) / 'images'
            images.mkdir()
            (images / 'first.png').write_bytes(b'first')
            jobs = MagicMock()
            jobs.submit.return_value = {'id': 'job', 'kind': 'image'}
            runtime = AsyncRuntime()
            app = create_desktop_app(state=DesktopState(Path(folder) / 'state'), runtime=runtime, job_manager=jobs, memory=MagicMock())
            client = app.test_client()
            token = client.post('/api/desktop/image-browser/open', json={'path': str(images)}).json['token']
            response = client.post('/api/desktop/media/generate', data={
                'operation': 'img2img', 'prompt': 'Combine', 'parameters': '{}',
                'references': (io.BytesIO(b'second'), 'second.jpg'),
                'reference_browser_token': token, 'reference_browser_path': 'first.png',
                'reference_order': json.dumps([1, 0]),
            })
            self.assertEqual(response.status_code, 202, response.json)
            self.assertEqual([item.data for item in jobs.submit.call_args.kwargs['references']], [b'first', b'second'])
