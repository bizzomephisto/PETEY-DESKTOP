/* TTIK: a responsive segmented voice display. No synthetic audio or mic capture. */
(() => {
    'use strict';
    const COLORS = {edge:'#514044',well:'#080507',dormant:'#2b1016',red:'#ff253b',mic:'#ef5968',muted:'#73545c'};
    window.createTTIKRenderer = context => {
        let output = 0;
        const polygon = (x,y,w,h,cut) => {
            context.beginPath(); context.moveTo(x+cut,y); context.lineTo(x+w-cut,y);
            context.lineTo(x+w,y+cut); context.lineTo(x+w,y+h-cut); context.lineTo(x+w-cut,y+h);
            context.lineTo(x+cut,y+h); context.lineTo(x,y+h-cut); context.lineTo(x,y+cut); context.closePath();
        };
        return scene => {
            const {width, height, delta, speechEnergy, micSamples, micActive, micMuted, state, mobile} = scene;
            const compact = height < 400;
            const availableHeight = compact ? height - 28 : height - (mobile ? 320 : 230);
            const unit = Math.max(.12, Math.min(width * (compact ? .45 : .82) / 330, availableHeight / 436, 1.45));
            const centerX = width * (compact ? .44 : .5);
            const centerY = compact ? height / 2 : (height + (mobile ? -80 : 10)) / 2;
            const target = state === 'speaking' ? Math.min(1,speechEnergy*1.6) : 0;
            output += (target-output)*(1-Math.exp(-delta/(target>output?45:160)));
            context.save(); context.globalAlpha = 1; context.globalCompositeOperation='source-over';
            context.translate(centerX - 165 * unit, centerY - 218 * unit); context.scale(unit,unit);
            const halo=context.createRadialGradient(165,203,30,165,203,280);
            halo.addColorStop(0,`rgba(205,10,32,${.04+output*.17})`); halo.addColorStop(1,'rgba(205,10,32,0)');
            context.fillStyle=halo; context.fillRect(-120,-70,570,590);
            context.shadowColor='#000'; context.shadowBlur=22*unit;
            polygon(0,0,330,436,36);
            const shell=context.createLinearGradient(0,0,330,436);
            shell.addColorStop(0,'#302327'); shell.addColorStop(.23,'#111013'); shell.addColorStop(1,'#1b1116');
            context.fillStyle=shell; context.fill(); context.shadowBlur=0;
            context.strokeStyle=COLORS.edge; context.lineWidth=1.5; context.stroke();
            polygon(8,8,314,420,32); context.strokeStyle='#35262c'; context.lineWidth=1; context.stroke();
            context.fillStyle='#d6b8bc'; context.font='600 12px ui-monospace,monospace'; context.textAlign='center'; context.fillText('T T I K',165,34);
            context.fillStyle='#7e646b'; context.font='7px ui-monospace,monospace'; context.fillText('VOICE INTERFACE',165,47);
            // Three recessed banks of twenty rectangular lamps, growing from the center.
            for(let column=0;column<3;column+=1) {
                const x=60+column*72;
                context.fillStyle=COLORS.well; context.fillRect(x-8,60,64,302);
                context.strokeStyle='#483039'; context.strokeRect(x-8,60,64,302);
                const reach=output*(column===1?10:7.8);
                for(let row=0;row<20;row+=1) {
                    const y=66+row*14.4, distance=Math.abs(row-9.5);
                    const standby=column===1 && distance<1 && state!=='muted' && state!=='error';
                    const strength = Math.max(standby ? .17 : 0, output > .005 ? Math.min(1, reach - distance + .65) : 0);
                    context.fillStyle=COLORS.dormant; context.fillRect(x,y,48,10.4);
                    context.strokeStyle='#51202a'; context.lineWidth=.6; context.strokeRect(x,y,48,10.4);
                    if(strength>.015) {
                        context.shadowColor=COLORS.red; context.shadowBlur=(5+strength*18)*unit;
                        context.fillStyle=`rgba(255,26,47,${strength})`; context.fillRect(x,y,48,10.4); context.shadowBlur=0;
                        const lamp=context.createLinearGradient(0,y,0,y+10.4);
                        lamp.addColorStop(0,`rgba(255,173,107,${strength*.6})`);
                        lamp.addColorStop(.5,`rgba(255,241,198,${strength*.98})`);
                        lamp.addColorStop(1,`rgba(255,112,65,${strength*.7})`);
                        context.fillStyle=lamp; context.fillRect(x+3,y+1.6,42,7.2);
                    }
                }
            }
            // Separate input scope: latest real mic PCM, flat when capture is inactive.
            context.fillStyle='#0b090c'; context.fillRect(50,375,230,34);
            context.strokeStyle='#39222b'; context.strokeRect(50,375,230,34);
            context.strokeStyle='#301d24'; context.lineWidth=.5;
            for(let grid=1;grid<8;grid+=1) {
                context.beginPath(); context.moveTo(50+grid*28.75,376); context.lineTo(50+grid*28.75,408); context.stroke();
            }
            context.strokeStyle=micActive?COLORS.mic:COLORS.muted; context.lineWidth=1.2;
            context.shadowColor=COLORS.mic; context.shadowBlur=micActive?5*unit:0; context.beginPath();
            for(let index=0;index<micSamples.length;index+=1) {
                const value=micActive?Math.max(-1,Math.min(1,micSamples[index]*6)):0;
                const x=53+index/(micSamples.length-1)*224,y=392-value*14;
                if(!index) context.moveTo(x,y); else context.lineTo(x,y);
            }
            context.stroke(); context.shadowBlur=0; context.fillStyle=micActive?'#eab6bc':COLORS.muted;
            context.font='7px ui-monospace,monospace'; context.fillText(micMuted?'MIC / MUTED':micActive?'MIC / LIVE':'MIC / OFF',165,422);
            for(const [x,y] of [[27,65],[303,65],[27,372],[303,372]]) {
                context.fillStyle='#09070a'; context.beginPath(); context.arc(x,y,4.3,0,Math.PI*2); context.fill();
                context.strokeStyle='#58434a'; context.lineWidth=.8; context.stroke();
                context.beginPath(); context.moveTo(x-2,y+1); context.lineTo(x+2,y-1); context.stroke();
            }
            context.restore();
        };
    };
})();
