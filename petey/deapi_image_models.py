"""Image model compatibility defaults; live catalog metadata takes precedence.

Source: https://docs.deapi.ai/models and deapi.ai/models (2026-10-14).
Only enrich discovered models, never advertise models unavailable to the account.
"""
from copy import deepcopy


def image_model_info(slug, info=None):
    partner = slug.startswith(('gpt-image-', 'nano-banana-'))
    counts = {'Flux_2_Klein_4B_BF16': 3, 'QwenImageEdit_Plus_NF4': 1,
              'gpt-image-1.5': 2, 'gpt-image-2': 2, 'gpt-image-2.5': 16,
              'nano-banana-2': 5, 'nano-banana-2.1': 5}
    fallback = {'limits': {}, 'features': {}, 'defaults': {}}
    if slug in counts:
        fallback['limits']['max_input_images'] = counts[slug]
        fallback['features'].update(supports_guidance=False, supports_negative_prompt=False)
    if partner:
        fallback['features'].update(supports_steps=False, supports_custom_output_size=True)
    if slug.startswith('gpt-image-'):
        fallback['limits']['quality_options'] = ['low', 'medium', 'high'] + (['auto'] if slug != 'gpt-image-1.5' else [])
        fallback['defaults']['quality'] = 'high' if slug == 'gpt-image-2.5' else 'medium'
    if slug == 'QwenImageEdit_Plus_NF4':
        fallback['features'].update(supports_negative_prompt=True, supports_steps=True, supports_custom_output_size=False)
        fallback['defaults']['steps'] = 40
    if slug == 'Flux_2_Klein_4B_BF16':
        fallback['limits'].update(min_steps=4, max_steps=4)
        fallback['defaults']['steps'] = 4
    result = deepcopy(info or {})
    for section, values in fallback.items():
        result[section] = {**values, **(result.get(section) or {})}
    return result
