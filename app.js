const $=s=>document.querySelector(s);let mode="analog",selectedFile=null,jobId=null,history=[],alerts=[],samples=[],chart;
let cameraStream=null;
const isLocalHost=["localhost","127.0.0.1"].includes(location.hostname);
const configuredApi=String(window.RETROSENSE_API_URL||"").trim();
// Local development uses the local FastAPI server. A deployed dashboard must be
// explicitly pointed at its Render API instead of incorrectly calling GitHub Pages.
const api=(configuredApi||(isLocalHost?"http://127.0.0.1:8000":"")).replace(/\/$/,"");
let apiToken="";
try{apiToken=sessionStorage.getItem("retrosense-api-token")||""}catch(_){}
function apiHeaders(){return apiToken?{"X-API-Token":apiToken}:{}}
async function authorizedFetch(url,options={},promptForToken=false){
  const headers=new Headers(options.headers||{});
  if(apiToken)headers.set("X-API-Token",apiToken);
  let response=await fetch(url,{...options,headers});
  if(response.status===401&&promptForToken){
    const entered=window.prompt("This RetroSense API is protected. Enter the API access token provided during Render deployment:");
    if(entered&&entered.trim()){
      apiToken=entered.trim();
      try{sessionStorage.setItem("retrosense-api-token",apiToken)}catch(_){}
      headers.set("X-API-Token",apiToken);
      response=await fetch(url,{...options,headers});
    }
  }
  return response;
}
const now=()=>new Date().toLocaleTimeString([],{hour:"2-digit",minute:"2-digit",second:"2-digit"});
function config(){return{min:Number($("#minValue").value)||0,max:Number($("#maxValue").value)||100,warning:Number($("#warningLimit").value)||75,danger:Number($("#dangerLimit").value)||90,unit:$("#unit").value,name:$("#machineName").value||"Instrument"}}
function status(v,c){return v>=c.danger?"DANGER":v>=c.warning?"WARNING":"NORMAL"}
function addReading(v,details={}){const c=config(),s=details.status||status(v,c),t=details.displayTime||now();$("#latestStat").textContent=v.toFixed(1);$("#unitStat").textContent=details.unit||c.unit;$("#gaugeValue").textContent=v.toFixed(1);$("#gaugeUnit").textContent=details.unit||c.unit;$("#updatedLabel").textContent=t;$("#readingTime").textContent="Updated at "+t;$("#instrumentStat").textContent="01";$("#modeStat").textContent=(details.mode||mode).toUpperCase();$("#alertStat").textContent=s;$("#alertStat").className=s==="NORMAL"?"status-normal":"";$("#alertStat").style.color=s==="DANGER"?"var(--red)":s==="WARNING"?"var(--amber)":"var(--green)";$("#minLabel").textContent=c.min;$("#maxLabel").textContent=c.max;const pct=Math.max(0,Math.min(1,(v-c.min)/(c.max-c.min||1)));$("#needle").style.transform=`rotate(${-135+pct*270}deg)`;$("#gaugeArc").style.strokeDashoffset=383.3*(1-pct);$("#gaugeArc").style.stroke=s==="DANGER"?"var(--red)":s==="WARNING"?"var(--amber)":"var(--cyan)";const row={time:details.timestamp||new Date().toISOString(),displayTime:t,name:details.instrument||c.name,value:v,unit:details.unit||c.unit,status:s,mode:details.mode||mode,job_id:details.job_id||null};history=history.filter(item=>!row.job_id||item.job_id!==row.job_id);history.unshift(row);history=history.slice(0,100);renderHistory();samples.push({x:t,y:v});samples=samples.slice(-20);chart.data.labels=samples.map(x=>x.x);chart.data.datasets[0].data=samples.map(x=>x.y);chart.update("none");if(s!=="NORMAL"&&(!alerts.length||alerts[0].status!==s)){alerts.unshift(row);renderAlerts()}persistDashboardState()}
function renderHistory(){$("#historyBody").innerHTML=history.length?history.slice(0,12).map(r=>`<tr><td>${r.displayTime}</td><td>${escapeHtml(r.name)}</td><td>${r.value.toFixed(1)}</td><td>${r.unit}</td><td><span class="pill-status ${r.status.toLowerCase()}">${r.status}</span></td></tr>`).join(""):'<tr><td colspan="5" class="empty">No readings yet.</td></tr>'}
function renderAlerts(){$("#alertCount").textContent=alerts.length+" EVENTS";$("#alerts").innerHTML=alerts.length?alerts.slice(0,8).map(a=>`<div class="alert-row ${a.status.toLowerCase()}"><i class="alert-dot"></i><div><b>${a.status}: ${a.value.toFixed(1)} ${a.unit}</b><small>${a.displayTime} · ${escapeHtml(a.name)}</small></div></div>`).join(""):'<div class="empty">No alerts detected. System is monitoring.</div>'}
function escapeHtml(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}

const STORAGE_KEY="retrosense.dashboard.v1";
function persistDashboardState(){
  try{localStorage.setItem(STORAGE_KEY,JSON.stringify({history:history.slice(0,100),alerts:alerts.slice(0,100)}))}
  catch(err){console.warn("RetroSense could not save local dashboard history:",err)}
}
async function syncServerHistory(){
  if(!api)return;
  try{
    const response=await fetch(api+"/api/readings",{headers:apiHeaders(),signal:AbortSignal.timeout(isLocalHost?5000:90000)});
    if(!response.ok)return;
    const payload=await response.json();
    const remote=(payload.readings||[]).map(item=>({
      time:item.timestamp,
      displayTime:new Date(item.timestamp).toLocaleTimeString(),
      name:item.instrument,
      value:Number(item.value),
      unit:item.unit,
      status:item.status,
      mode:item.mode,
      job_id:item.job_id
    })).filter(item=>Number.isFinite(item.value));
    const known=new Set(history.map(item=>item.job_id).filter(Boolean));
    history=[...remote.filter(item=>!known.has(item.job_id)),...history].slice(0,100);
    const alertKeys=new Set(alerts.map(item=>item.job_id).filter(Boolean));
    alerts=[...remote.filter(item=>item.status!=="NORMAL"&&!alertKeys.has(item.job_id)),...alerts].slice(0,100);
    persistDashboardState();
    restoreDashboardState();syncServerHistory();
    $("#apiStatus").textContent="ONLINE";
  }catch(err){console.warn("Could not sync server history:",err)}
}
function restoreDashboardState(){
  try{
    const saved=JSON.parse(localStorage.getItem(STORAGE_KEY)||"{}");
    const valid=row=>row&&Number.isFinite(Number(row.value))&&typeof row.displayTime==="string"&&typeof row.name==="string";
    history=Array.isArray(saved.history)?saved.history.filter(valid).slice(0,100):[];
    alerts=Array.isArray(saved.alerts)?saved.alerts.filter(valid).slice(0,100):[];
  }catch(err){history=[];alerts=[];console.warn("RetroSense local history could not be read:",err)}
  renderHistory();renderAlerts();
  if(!history.length)return;
  const latest=history[0],c=config(),value=Number(latest.value),s=latest.status;
  $("#latestStat").textContent=value.toFixed(1);$("#unitStat").textContent=latest.unit||c.unit;
  $("#gaugeValue").textContent=value.toFixed(1);$("#gaugeUnit").textContent=latest.unit||c.unit;
  $("#readingTime").textContent="Restored from this browser · "+latest.displayTime;
  $("#updatedLabel").textContent=latest.displayTime;$("#instrumentStat").textContent="01";
  $("#modeStat").textContent=mode.toUpperCase();$("#alertStat").textContent=s||"UNKNOWN";
  $("#alertStat").style.color=s==="DANGER"?"var(--red)":s==="WARNING"?"var(--amber)":"var(--green)";
  const pct=Math.max(0,Math.min(1,(value-c.min)/(c.max-c.min||1)));
  $("#needle").style.transform=`rotate(${-135+pct*270}deg)`;
  $("#gaugeArc").style.strokeDashoffset=383.3*(1-pct);
  samples=history.slice(0,20).reverse().map(r=>({x:r.displayTime,y:Number(r.value)}));
  chart.data.labels=samples.map(x=>x.x);chart.data.datasets[0].data=samples.map(x=>x.y);chart.update("none");
}
function initChart(){const ctx=$("#trendChart");chart=new Chart(ctx,{type:"line",data:{labels:[],datasets:[{data:[],borderColor:"#53d6d0",backgroundColor:"rgba(83,214,208,.08)",fill:true,tension:.35,pointRadius:2,pointBackgroundColor:"#53d6d0",borderWidth:2}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{color:"rgba(130,150,170,.08)"},ticks:{color:"#718293",maxTicksLimit:6,font:{size:9}}},y:{grid:{color:"rgba(130,150,170,.1)"},ticks:{color:"#718293",font:{size:9}}}}}})}
document.querySelectorAll(".mode").forEach(b=>b.addEventListener("click",()=>{document.querySelectorAll(".mode").forEach(x=>x.classList.remove("active"));b.classList.add("active");mode=b.dataset.mode;$("#modeStat").textContent=mode.toUpperCase()}));
$("#fileInput").addEventListener("change",e=>{selectedFile=e.target.files[0];$("#fileName").textContent=selectedFile?selectedFile.name:"No file selected"});
$("#dropzone").addEventListener("dragover",e=>{e.preventDefault();e.currentTarget.style.borderColor="var(--cyan)"});
$("#dropzone").addEventListener("dragleave",e=>e.currentTarget.style.borderColor="");
$("#dropzone").addEventListener("drop",e=>{e.preventDefault();e.currentTarget.style.borderColor="";selectedFile=e.dataTransfer.files[0];if(selectedFile){$("#fileInput").files=e.dataTransfer.files;$("#fileName").textContent=selectedFile.name}});
async function startCapture(){
  const c=config();
  if(mode==="analog"&&c.max<=c.min){alert("Maximum value must be greater than minimum value.");return}
  if(c.danger<c.warning){alert("Danger threshold must be greater than or equal to warning threshold.");return}
  if(!selectedFile){alert("Choose an instrument image first.");return}
  if(!api){$("#apiStatus").textContent="NOT CONFIGURED";alert("RetroSense API is not configured for this deployed dashboard. Deploy the FastAPI backend to Render, then set window.RETROSENSE_API_URL in index.html to the Render service URL.");return}
  if(selectedFile.type.startsWith("video/")){alert("Video processing is not implemented yet. Capture a still frame or upload an image.");return}
  const btn=$("#analyzeBtn");btn.disabled=true;btn.textContent="Analyzing image…";
  try{
    const health=await fetch(api+"/api/health",{signal:AbortSignal.timeout(isLocalHost?5000:90000)});
    if(!health.ok)throw Error("API unavailable");
    $("#apiStatus").textContent="ONLINE";
    const fd=new FormData();
    fd.append("file",selectedFile);fd.append("mode",mode);fd.append("machine_name",c.name);fd.append("unit",c.unit);
    fd.append("min_value",c.min);fd.append("max_value",c.max);fd.append("warning_limit",c.warning);fd.append("danger_limit",c.danger);
    fd.append("start_angle",$("#startAngle").value);fd.append("end_angle",$("#endAngle").value);
    const createdResponse=await authorizedFetch(api+"/api/jobs",{method:"POST",body:fd},true);
    const created=await createdResponse.json();
    if(!createdResponse.ok)throw Error(created.detail||"Could not create analysis job");
    jobId=created.job_id;
    const resultResponse=await authorizedFetch(api+`/api/jobs/${jobId}/start`,{method:"POST"},true);
    const result=await resultResponse.json();
    if(!resultResponse.ok)throw Error(result.detail||"Image analysis failed");
    const reading=result.reading;
    const analysis=reading.analysis||{};
    addReading(Number(reading.value),{
      timestamp:reading.timestamp,instrument:reading.instrument,unit:reading.unit,
      status:reading.status,mode:reading.mode,job_id:jobId,
      displayTime:new Date(reading.timestamp).toLocaleTimeString()
    });
    $("#readingTime").textContent=(mode==="digital"?"OCR estimate · ":"CV estimate · ")+now();
    $("#cameraStatus").textContent=$("#cameraPanel").hidden?"Camera is off.":"Frame analyzed. Capture another frame or close the camera.";
    alert(mode==="digital"?
      "OCR reading: "+reading.value+" "+reading.unit+"\nRecognized text: "+(analysis.raw_text||"")+
      "\nOCR score: "+(analysis.confidence??"not available")+" (not measurement accuracy). Verify manually.":
      "Estimated reading: "+reading.value+" "+reading.unit+"\nPointer angle: "+
      (analysis.pointer_angle_deg??"not available")+"°\nConfidence: experimental. Verify manually.");
  }catch(err){
    $("#apiStatus").textContent="OFFLINE";
    alert("Could not analyze this image.\n"+err.message+"\n\nCheck that the FastAPI backend is running and the image/calibration is suitable.");
  }finally{btn.disabled=false;btn.innerHTML='Analyze instrument <span>→</span>'}
}
function runDemo(){const c=config();let n=0;const timer=setInterval(()=>{const v=Math.max(c.min,Math.min(c.max,c.min+(c.max-c.min)*(.56+.12*Math.sin(n/3)+.025*(Math.random()-.5))));addReading(v);n++;if(n>=20)clearInterval(timer)},850)}
function connectSocket(id){const ws=new WebSocket(api.replace("http","ws")+`/ws/jobs/${id}`);ws.onmessage=e=>{const d=JSON.parse(e.data);if(typeof d.value==="number")addReading(d.value)};ws.onclose=()=>$("#apiStatus").textContent="ONLINE"}
async function openCamera(){
  const panel=$("#cameraPanel"),video=$("#cameraVideo"),start=$("#cameraStart"),capture=$("#cameraCapture"),stop=$("#cameraStop"),status=$("#cameraStatus");
  if(!navigator.mediaDevices?.getUserMedia){status.textContent="Camera access is unavailable. Use HTTPS or localhost, or upload an image.";panel.hidden=false;return}
  try{
    cameraStream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:"environment"},width:{ideal:1280},height:{ideal:720}},audio:false});
    video.srcObject=cameraStream;panel.hidden=false;await video.play();
    start.disabled=true;capture.disabled=false;stop.disabled=false;status.textContent="Camera is ready. Position the instrument and capture a frame.";
  }catch(err){panel.hidden=false;status.textContent="Could not open camera: "+err.message+". Check browser camera permission or upload an image."}
}
function closeCamera(){
  if(cameraStream){cameraStream.getTracks().forEach(track=>track.stop());cameraStream=null}
  const video=$("#cameraVideo");if(video)video.srcObject=null;
  $("#cameraStart").disabled=false;$("#cameraCapture").disabled=true;$("#cameraStop").disabled=true;
  $("#cameraStatus").textContent="Camera is off.";
}
async function captureCameraFrame(){
  const video=$("#cameraVideo"),canvas=$("#cameraCanvas");
  if(!cameraStream||!video.videoWidth||!video.videoHeight){$("#cameraStatus").textContent="Camera is not ready yet.";return}
  canvas.width=video.videoWidth;canvas.height=video.videoHeight;
  const context=canvas.getContext("2d");context.drawImage(video,0,0,canvas.width,canvas.height);
  const blob=await new Promise(resolve=>canvas.toBlob(resolve,"image/jpeg",0.92));
  if(!blob){$("#cameraStatus").textContent="Could not capture this frame. Try again.";return}
  selectedFile=new File([blob],"retrosense-camera-"+Date.now()+".jpg",{type:"image/jpeg"});
  $("#fileName").textContent=selectedFile.name+" · camera frame";
  $("#cameraStatus").textContent="Frame captured. Sending image for analysis…";
  await startCapture();
}
$("#cameraStart").addEventListener("click",openCamera);
$("#cameraCapture").addEventListener("click",captureCameraFrame);
$("#cameraStop").addEventListener("click",closeCamera);
window.addEventListener("pagehide",closeCamera);
$("#analyzeBtn").addEventListener("click",startCapture);
$("#exportBtn").addEventListener("click",()=>{if(!history.length){alert("No readings available to export.");return}const rows=[["timestamp","instrument","reading","unit","status"],...history.map(r=>[r.time,r.name,r.value,r.unit,r.status])];const csv=rows.map(r=>r.map(v=>'"'+String(v).replace(/"/g,'""')+'"').join(",")).join("\n");const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([csv],{type:"text/csv"}));a.download="retrosense-readings.csv";a.click();URL.revokeObjectURL(a.href)});
initChart();$("#latestStat").textContent="—";$("#gaugeValue").textContent="—";$("#alertStat").textContent="WAITING";$("#alertStat").style.color="var(--muted)";$("#readingTime").textContent="No image analyzed yet";$("#updatedLabel").textContent="—";restoreDashboardState();
