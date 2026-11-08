"""Fish voice browser checks using temporary state and synthetic audio only."""
from pathlib import Path
import unittest

from browser_fixture import DesktopBrowserFixture


class FishVoiceRegressions(DesktopBrowserFixture):
    def fish_settings(self):
        self.responses['speech']['configuration'].update({'provider': 'fish', 'fish_voice': 'test-voice',
            'fish_emotions': True, 'fish_streaming': True, 'fish_show_cues': False})
        self.view('personality')
        self.page.evaluate("""()=>{
            document.getElementById('speech-settings-card').open = true;
            speechConfiguration = {...speechConfiguration, provider:'fish', fish_voice:'test-voice',
                fish_emotions:true, fish_streaming:true, fish_show_cues:false};
            fillSpeechForm(speechConfiguration);
        }""")

    def test_fish_controls_and_cue_visibility_on_desktop_and_phone(self):
        self.fish_settings()
        def save(route):
            changes = route.request.post_data_json
            self.responses['speech']['configuration'].update(changes)
            route.fulfill(json=self.responses['speech'])
        self.context.route('**/api/desktop/speech', save)
        self.page.evaluate("""()=>{
            addMessage('assistant', '[[fish:dryly sarcastic]] Sure. [1, 2, 3] [Docs](https://example.com)');
            addMessage('user', 'Keep [my brackets].');
        }""")
        bubble = self.page.locator('.message.assistant .bubble').last
        self.assertNotIn('sarcastic', bubble.inner_text())
        self.assertEqual(bubble.locator('a').get_attribute('href'), 'https://example.com')
        for width in (1440, 390):
            self.viewport(width)
            self.view('personality')
            self.page.locator('#speech-fish-show-cues').check()
            self.page.wait_for_function("speechConfiguration.fish_show_cues===true")
            self.assertIn('[dryly sarcastic]', bubble.inner_text())
            self.assertIn('[1, 2, 3]', bubble.inner_text())
            self.page.locator('#speech-fish-show-cues').uncheck()
            self.page.wait_for_function("speechConfiguration.fish_show_cues===false")
            self.assertNotIn('sarcastic', bubble.inner_text())
            self.assertEqual(self.page.locator('.message.user .bubble').last.inner_text(), 'Keep [my brackets].')
            self.page.locator('#speech-fish-emotions').uncheck()
            self.page.locator('#speech-fish-streaming').uncheck()
            values = self.page.evaluate('readSpeechForm()')
            self.assertFalse(values['fish_emotions'])
            self.assertFalse(values['fish_streaming'])
            self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth>innerWidth'))
            self.page.screenshot(path=f'/tmp/petey-fish-settings-{width}.png', full_page=True)

    def test_fish_partial_cues_do_not_flash_and_normal_brackets_survive(self):
        result = self.page.evaluate("""()=>({
            partial:fishChatText('Hello [[fish:cur',false,true),
            plain:fishChatText('Array [1, 2] and [Docs](https://example.com)'),
            marker:fishChatText('[[fish:warm and curious]] Hello',true),
            short:firstStreamingSpeechSegment('[[fish:curious]] Hello. What do you think?',12),
            split:firstStreamingSpeechSegment('x'.repeat(160)+' [[fish:very warm and curious]] '+ 'word '.repeat(15),12),
        })""")
        self.assertEqual(result['partial'], 'Hello ')
        self.assertEqual(result['plain'], 'Array [1, 2] and [Docs](https://example.com)')
        self.assertEqual(result['marker'], '[warm and curious] Hello')
        self.assertEqual(result['short'], '[[fish:curious]] Hello.')
        self.assertNotIn('[[fish:', result['split'])

    def install_stream_fixture(self):
        self.page.evaluate("""()=>{
            speechConfiguration = {...speechConfiguration,provider:'fish',fish_streaming:true};
            window.fishQueued=0;
            window.fishStarted=0; window.fishStopped=0; window.fishRequestCount=0;
            const context={state:'running',currentTime:0,resume:async()=>{},
                createBuffer:(_channels,length,rate)=>({duration:length/rate,copyToChannel:()=>{}}),
                createBufferSource:()=>({connect:()=>{}, start(){fishStarted++;queueMicrotask(()=>this.onended?.());},stop(){fishStopped++;}})};
            getSpeechPlaybackContext=()=>context;
            primeSpeechPlayback=()=>{};  // This fixture tests streaming, not audio unlock.
            speechVisualizationOutput=()=>({});
            const realFetch=window.fetch;
            window.fetch=async(url,options)=>{
                if(url==='/api/desktop/chat/speech'){fishQueued++;return new Response('{"error":"Unexpected queued retry"}',{status:503});}
                if(url!=='/api/desktop/chat/speech/stream')return realFetch(url,options);
                fishRequestCount++;
                return new Response(new ReadableStream({start(controller){
                    window.fishStream=controller;
                    options.signal.addEventListener('abort',()=>controller.error(new DOMException('Stopped','AbortError')));
                    const encoder=new TextEncoder();
                    controller.enqueue(encoder.encode('{"status":"connecting","provider":"fish"}\\n{"audio":"AQACAA=="}\\n'));
                }}),{headers:{'Content-Type':'application/x-ndjson'}});
            };
        }""")

    def test_fish_plays_before_stream_finishes_and_cancels_without_replay(self):
        self.install_stream_fixture()
        self.page.evaluate("""()=>{window.fishResult='pending';window.fishPlayback=playChatSpeechStream('Hello',null).then(()=>fishResult='done').catch(e=>fishResult=e.name);} """)
        self.page.wait_for_function('fishStarted===1')
        self.assertEqual(self.page.evaluate('fishResult'), 'pending')
        self.page.evaluate("fishStream.enqueue(new TextEncoder().encode('{\"status\":\"done\"}\\n'));fishStream.close()")
        self.page.wait_for_function("fishResult==='done'")
        self.page.evaluate("""()=>{window.fishResult='pending';window.fishPlayback=playChatSpeechStream('Hello',null).then(()=>fishResult='done').catch(e=>fishResult=e.name);} """)
        self.page.wait_for_function('fishStarted===2')
        self.page.evaluate('activeSpeechCancel()')
        self.page.wait_for_function("fishResult==='AbortError'")
        self.assertEqual(self.page.evaluate('fishRequestCount'), 2)

    def test_fish_failure_after_audio_never_replays_through_job_queue(self):
        self.install_stream_fixture()
        self.page.evaluate("""()=>{window.fishFinished=false;window.fishPlayback=speakChatText('Hello').finally(()=>fishFinished=true);}""")
        self.page.wait_for_function('fishStarted===1')
        self.page.evaluate("fishStream.error(new Error('Fixture disconnected'))")
        self.page.wait_for_function('fishFinished')
        self.assertEqual(self.page.evaluate('fishRequestCount'), 1)
        self.assertEqual(self.page.evaluate('fishQueued'), 0)
        self.assertIn('Fixture disconnected', self.page.locator('#status').inner_text())

    def test_fish_visibility_save_failure_restores_switch(self):
        self.fish_settings()
        self.context.route('**/api/desktop/speech', lambda route:route.fulfill(status=503,json={'error':'Save failed'}))
        self.page.locator('#speech-fish-show-cues').check()
        self.page.wait_for_function("!document.getElementById('speech-fish-show-cues').disabled")
        self.assertFalse(self.page.locator('#speech-fish-show-cues').is_checked())
        self.assertIn('Save failed', self.page.locator('#speech-settings-status').inner_text())

    def test_fish_inline_directions_and_word_spans_show_hide_as_text(self):
        result = self.page.evaluate("""()=>{
            const raw='[[fish:surprised]][[fish:gasping]] Wait, [[fish:<emphasis>]]HOLY SHIT![[fish:</emphasis>]] [[fish:soft tone]]It worked.';
            speechConfiguration={...speechConfiguration,fish_show_cues:false};
            addMessage('assistant',raw);
            const bubble=messages.querySelector('.message.assistant:last-child .bubble');
            const hidden=bubble.textContent;
            speechConfiguration.fish_show_cues=true;refreshFishCueVisibility();
            return {hidden,shown:bubble.textContent,htmlTags:bubble.querySelectorAll('emphasis').length,
                partial:fishChatText('Wait [[fish:<emphasis>]',false,true)};
        }""")
        self.assertEqual(result['hidden'], 'Wait, HOLY SHIT! It worked.')
        self.assertIn('[surprised][gasping]', result['shown'])
        self.assertIn('<emphasis>HOLY SHIT!</emphasis>', result['shown'])
        self.assertEqual(result['htmlTags'], 0)
        self.assertEqual(result['partial'], 'Wait ')

    def test_fish_sentence_streaming_never_splits_emphasis_span(self):
        result=self.page.evaluate("""()=>{
            const raw='Before [[fish:<emphasis>]]HOLY SHIT! This is big.[[fish:</emphasis>]] Then breathe.';
            const segment=firstStreamingSpeechSegment(raw,12);
            const long='[[fish:<emphasis>]]'+ 'important '.repeat(30)+'[[fish:</emphasis>]] Done.';
            return {segment,balanced:fishSafeSpeechBoundary(raw,segment.length)===segment.length,
                incomplete:firstStreamingSpeechSegment('[[fish:<emphasis>]]'+ 'important '.repeat(30),12),
                completed:firstStreamingSpeechSegment(long,12),
                inline:firstStreamingSpeechSegment('[[fish:curious]][[fish:whispering]] This is [[fish:emphasis]]really important. Next.',12)};
        }""")
        self.assertIn('[[fish:</emphasis>]]', result['segment'])
        self.assertTrue(result['balanced'])
        self.assertEqual(result['incomplete'], '')
        self.assertIn('[[fish:</emphasis>]]', result['completed'])
        self.assertIn('[[fish:emphasis]]really important.', result['inline'])


if __name__ == '__main__':
    names = [name for name in unittest.defaultTestLoader.getTestCaseNames(FishVoiceRegressions)
             if name.startswith('test_fish_')]
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(FishVoiceRegressions(name) for name in names))
    raise SystemExit(not result.wasSuccessful())
