'use strict';
// Media occupies layout only after a usable asset has loaded.
const boardSection=$('board').closest('section'),cadSection=$('mesh').closest('section');
boardSection.hidden=true;cadSection.hidden=true;
const boardReady=()=>{boardSection.hidden=!($('board').complete&&$('board').naturalWidth>0);};
$('board').addEventListener('load',boardReady);$('board').addEventListener('error',()=>boardSection.hidden=true);boardReady();
const initialModelLoader=loadModel;
loadModel=async function(){await initialModelLoader();cadSection.hidden=!$('mesh-status').textContent.includes('triangles')||!ctx;if(!cadSection.hidden){const caption=$('mesh-status').textContent.split(' · ')[0];$('mesh-status').textContent=caption+' · '+$('model').selectedOptions[0].textContent+' · wireframe';}};
$('model').onchange=loadModel;
const observer=new MutationObserver(()=>{cadSection.hidden=!$('mesh-status').textContent.includes('triangles')||!ctx;});observer.observe($('mesh-status'),{childList:true,subtree:true,characterData:true});
const originalBoardChange=$('pcb').onchange;$('pcb').onchange=()=>{boardSection.hidden=true;originalBoardChange();};
const photosSection=$('photo-results').closest('details');photosSection.hidden=true;
loadPhotos().catch(e=>console.info('Development media:',e.message));
