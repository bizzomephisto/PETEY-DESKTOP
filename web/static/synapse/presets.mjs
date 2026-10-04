export const PRESET_STORAGE_KEY='petey-network-presets-v1';
const ranges={hoverRadius:[40,400],hoverStrength:[0,2],layers:[2,48],neurons:[2,64],connections:[1,64],speed:[.05,10],activity:[.05,1],motion:[0,3],glow:[0,3],brightness:[0,2],routeChance:[0,1],signalWidth:[.1,20],nodeSize:[.1,10],scaleX:[.1,10],scaleY:[.1,10],seed:[0,2147483647]};
const enums={hoverMode:['attract','repel','glow','off'],theme:['black','aurora','ember','dark','light'],nodeStyle:['soft','solid','ring','diamond'],nodeColor:['theme','neutral','custom']};
const booleans=['showNodes','fullLength','quiet'];
export function presetSettings(value,defaults){
 defaults={hoverMode:'attract',hoverRadius:140,hoverStrength:.65,...defaults};
 const result={};
 for(const [key,[min,max]] of Object.entries(ranges)){const raw=typeof value?.[key]==='number'&&Number.isFinite(value[key])?value[key]:defaults[key];result[key]=Math.max(min,Math.min(max,raw));if(['layers','neurons','connections','seed'].includes(key))result[key]=Math.round(result[key]);}
 result.connections=Math.min(result.connections,result.neurons);
 for(const [key,options] of Object.entries(enums))result[key]=options.includes(value?.[key])?value[key]:defaults[key];
 for(const key of booleans)result[key]=typeof value?.[key]==='boolean'?value[key]:defaults[key];
 result.nodeCustom=/^#[0-9a-f]{6}$/i.test(value?.nodeCustom)?value.nodeCustom:defaults.nodeCustom;
 return result;
}
export function readPresets(storage,defaults){
 const raw=storage.getItem(PRESET_STORAGE_KEY);if(!raw)return [];
 const document=JSON.parse(raw);if(document.version!==1||!Array.isArray(document.presets))throw new Error('Invalid preset data');
 const entries=new Map();
 for(const entry of document.presets){if(!entry||typeof entry.name!=='string'||!entry.name.trim()||!entry.settings||typeof entry.settings!=='object')continue;const name=entry.name.trim().slice(0,60);entries.set(name,{name,settings:presetSettings(entry.settings,defaults)});}
 return [...entries.values()];
}
export function writePresets(storage,presets){storage.setItem(PRESET_STORAGE_KEY,JSON.stringify({version:1,presets}));}
