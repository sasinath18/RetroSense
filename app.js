const $=s=>document.querySelector(s);let mode="analog",selectedFile=null,jobId=null,history=[],alerts=[],samples=[],chart;
let cameraStream=null,cameraTimer=null,autoCaptureRequested=false,isAnalyzing=false,previewUrl=null;
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
function numericInput(selector,label){
  const raw=$(selector).value.trim();
  const value=Number(raw);
  if(raw===""||!Number.isFinite(value))throw Error(label+" must be a valid number.");
  return value;
}
function config(){
  return{
    min:numericInput("#minValue","Minimum value"),
    max:numericInput("#maxValue","Maximum value"),
    warning:numericInput("#warningLimit","Warning threshold"),
    danger:numericInput("#dangerLimit","Danger threshold"),
    unit:$("#unit").value,
    name:$("#machineName").value.trim()||"Instrument"
  };
}
function status(v,c){return v>=c.danger?"DANGER":v>=c.warning?"WARNING":"NORMAL"}
function updateGauge(value,c){
  const pct=Math.max(0,Math.min(1,(value-c.min)/(c.max-c.min)));
  $("#needle").setAttribute("transform",`rotate(${-90+pct*180} 160 160)`);
  $("#gaugeArc").style.strokeDashoffset=383.3*(1-pct);
  $("#minLabel").textContent=c.min;
  $("#maxLabel").textContent=c.max;
}
function addReading(v,details={}){
  if(!Number.isFinite(v))throw Error("The backend returned an invalid numeric reading.");
  const c=config(),s=details.status||status(v,c),t=details.displayTime||now();
  $("#latestStat").textContent=v.toFixed(1);$("#unitStat").textContent=details.unit||c.unit;
  $("#gaugeValue").textContent=v.toFixed(1);$("#gaugeUnit").textContent=details.unit||c.unit;
  $("#updatedLabel").textContent=t;$("#readingTime").textContent="Updated at "+t;
  $("#instrumentStat").textContent=String(new Set([c.name,...history.map(item=>item.name)]).size).padStart(2,"0");
  $("#modeStat").textContent=(details.mode||mode).toUpperCase();
  $("#alertStat").textContent=s;$("#alertStat").className=s==="NORMAL"?"status-normal":"";
  $("#alertStat").style.color=s==="DANGER"?"var(--red)":s==="WARNING"?"var(--amber)":"var(--green)";
  updateGauge(v,c);
  $("#gaugeArc").style.stroke=s==="DANGER"?"var(--red)":s==="WARNING"?"var(--amber)":"var(--cyan)";
  const row={
    time:details.timestamp||new Date().toISOString(),displayTime:t,
    name:details.instrument||c.name,value:v,unit:details.unit||c.unit,
    status:s,mode:details.mode||mode,job_id:details.job_id||null,
    min:c.min,max:c.max,warning:c.warning,danger:c.danger
  };
  history=history.filter(item=>!row.job_id||item.job_id!==row.job_id);
  history.unshift(row);history=history.slice(0,100);renderHistory();
  samples.push({x:t,y:v});samples=samples.slice(-20);
  chart.data.labels=samples.map(item=>item.x);
  chart.data.datasets[0].data=samples.map(item=>item.y);
  chart.update("none");
  if(s!=="NORMAL"&&(!alerts.length||alerts[0].job_id!==row.job_id)){
    alerts.unshift(row);alerts=alerts.slice(0,100);renderAlerts();
  }
  persistDashboardState();
}
function renderHistory(){$("#historyBody").innerHTML=history.length?history.slice(0,12).map(r=>{const s=["NORMAL","WARNING","DANGER"].includes(r.status)?r.status:"UNKNOWN";return `<tr><td>${escapeHtml(r.displayTime)}</td><td>${escapeHtml(r.name)}</td><td>${Number(r.value).toFixed(1)}</td><td>${escapeHtml(r.unit||"")}</td><td><span class="pill-status ${s.toLowerCase()}">${s}</span></td></tr>`}).join(""):'<tr><td colspan="5" class="empty">No readings yet.</td></tr>'}
function renderAlerts(){$("#alertCount").textContent=alerts.length+" EVENTS";$("#alerts").innerHTML=alerts.length?alerts.slice(0,8).map(a=>{const s=["NORMAL","WARNING","DANGER"].includes(a.status)?a.status:"UNKNOWN";return `<div class="alert-row ${s.toLowerCase()}"><i class="alert-dot"></i><div><b>${s}: ${Number(a.value).toFixed(1)} ${escapeHtml(a.unit||"")}</b><small>${escapeHtml(a.displayTime)} · ${escapeHtml(a.name)}</small></div></div>`}).join(""):'<div class="empty">No alerts detected. System is monitoring.</div>'}
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
    if(response.status===401){$("#apiStatus").textContent="TOKEN REQUIRED";return}
    if(!response.ok)throw Error("Reading history request failed ("+response.status+")");
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
    restoreDashboardState();
    $("#apiStatus").textContent="ONLINE";
  }catch(err){console.warn("Could not sync server history:",err)}
}
function restoreDashboardState(){
  try{
    const saved=JSON.parse(localStorage.getItem(STORAGE_KEY)||"{}");
    const valid=row=>row&&Number.isFinite(Number(row.value))&&typeof row.displayTime==="string"&&typeof row.name==="string";
    history=Array.isArray(saved.history)?saved.history.filter(valid).map(row=>({...row,value:Number(row.value)})).slice(0,100):[];
    alerts=Array.isArray(saved.alerts)?saved.alerts.filter(valid).map(row=>({...row,value:Number(row.value)})).slice(0,100):[];
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
  $("#needle").setAttribute("transform",`rotate(${-90+pct*180} 160 160)`);
  $("#gaugeArc").style.strokeDashoffset=383.3*(1-pct);
  samples=history.slice(0,20).reverse().map(r=>({x:r.displayTime,y:Number(r.value)}));
  chart.data.labels=samples.map(x=>x.x);chart.data.datasets[0].data=samples.map(x=>x.y);chart.update("none");
}
function initChart(){
  const canvas=$("#trendChart");
  const emptyData={labels:[],datasets:[{data:[]}]};
  if(typeof window.Chart==="function"){
    chart=new window.Chart(canvas,{
      type:"line",
      data:{labels:[],datasets:[{
        data:[],borderColor:"#53d6d0",backgroundColor:"rgba(83,214,208,.08)",
        fill:true,tension:.35,pointRadius:3,pointBackgroundColor:"#53d6d0",borderWidth:2
      }]},
      options:{
        responsive:true,maintainAspectRatio:false,animation:false,
        plugins:{legend:{display:false}},
        scales:{
          x:{grid:{color:"rgba(130,150,170,.08)"},ticks:{color:"#718293",maxTicksLimit:6,font:{size:9}}},
          y:{grid:{color:"rgba(130,150,170,.1)"},ticks:{color:"#718293",font:{size:9}}}
        }
      }
    });
    return;
  }

  // Native canvas fallback keeps the dashboard functional when the Chart.js CDN
  // is unavailable, blocked or offline.
  const context=canvas.getContext("2d");
  const draw=()=>{
    const rect=canvas.getBoundingClientRect();
    const width=Math.max(280,rect.width||280),height=Math.max(180,rect.height||190);
    const ratio=window.devicePixelRatio||1;
    canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);
    context.setTransform(ratio,0,0,ratio,0,0);
    context.clearRect(0,0,width,height);
    const values=emptyData.datasets[0].data.map(Number).filter(Number.isFinite);
    const min=values.length?Math.min(...values):0,max=values.length?Math.max(...values):100;
    const spread=Math.max(max-min,1),low=Math.max(0,min-spread*.12),high=max+spread*.12;
    const left=42,right=12,top=12,bottom=28,plotW=width-left-right,plotH=height-top-bottom;
    context.font="10px Arial";context.textAlign="right";context.textBaseline="middle";
    for(let i=0;i<=4;i++){
      const y=top+plotH*i/4,value=high-(high-low)*i/4;
      context.strokeStyle="rgba(130,150,170,.16)";context.lineWidth=1;
      context.beginPath();context.moveTo(left,y);context.lineTo(width-right,y);context.stroke();
      context.fillStyle="#81909f";context.fillText(value.toFixed(1),left-7,y);
    }
    if(!values.length){
      context.fillStyle="#81909f";context.textAlign="center";
      context.fillText("No readings yet",width/2,height/2);return;
    }
    const xAt=i=>values.length===1?left+plotW/2:left+plotW*i/(values.length-1);
    const yAt=value=>top+(high-value)/(high-low)*plotH;
    context.beginPath();
    values.forEach((value,i)=>{const x=xAt(i),y=yAt(value);if(i===0)context.moveTo(x,y);else context.lineTo(x,y)});
    context.strokeStyle="#53d6d0";context.lineWidth=2;context.stroke();
    values.forEach((value,i)=>{
      context.beginPath();context.arc(xAt(i),yAt(value),3,0,Math.PI*2);
      context.fillStyle="#53d6d0";context.fill();
    });
    context.fillStyle="#81909f";context.textAlign="left";
    const labels=emptyData.labels;
    if(labels.length)context.fillText(String(labels[0]).slice(0,12),left,height-10);
    if(labels.length>2){context.textAlign="center";context.fillText(String(labels[Math.floor(labels.length/2)]).slice(0,12),left+plotW/2,height-10)}
    if(labels.length>1){context.textAlign="right";context.fillText(String(labels[labels.length-1]).slice(0,12),width-right,height-10)}
  };
  chart={data:emptyData,update:draw};
  window.addEventListener("resize",draw);
  draw();
}
function initGaugeTicks(){
  const group=$("#ticks");
  if(!group)return;
  const ns="http://www.w3.org/2000/svg",cx=160,cy=160,outer=114;
  group.replaceChildren();
  for(let i=0;i<=20;i++){
    const fraction=i/20,angle=Math.PI*(1-fraction);
    const inner=outer-(i%2===0?12:6);
    const x1=cx+Math.cos(angle)*inner,y1=cy-Math.sin(angle)*inner;
    const x2=cx+Math.cos(angle)*outer,y2=cy-Math.sin(angle)*outer;
    const line=document.createElementNS(ns,"line");
    line.setAttribute("x1",x1);line.setAttribute("y1",y1);line.setAttribute("x2",x2);line.setAttribute("y2",y2);
    line.setAttribute("stroke",i%2===0?"#81909f":"#4c5c6b");line.setAttribute("stroke-width",i%2===0?"2":"1");
    group.appendChild(line);
  }
}
function setApiState(state){
  const el=$("#apiStatus"),pill=$("#systemState");
  if(el){el.textContent=state;el.dataset.state=state.toLowerCase().replaceAll(" ","-")}
  if(pill){
    const label=state==="ONLINE"?"API CONNECTED":state==="CONNECTING"?"CONNECTING":state==="TOKEN REQUIRED"?"TOKEN REQUIRED":state==="NOT CONFIGURED"?"API NOT CONFIGURED":state==="OFFLINE"?"API OFFLINE":"SYSTEM";
    pill.lastChild.textContent=label;
    pill.classList.toggle("is-offline",state==="OFFLINE"||state==="NOT CONFIGURED");
    pill.classList.toggle("is-pending",state==="CONNECTING"||state==="TOKEN REQUIRED");
  }
}
function showSelectedFile(file){
  const allowed=["image/jpeg","image/png","image/webp","image/bmp"];
  if(!file){selectedFile=null;$("#fileName").textContent="No file selected";$("#selectedPreview").hidden=true;return false}
  if(!allowed.includes(file.type)){
    alert("Unsupported file type. Choose a JPG, PNG, WEBP or BMP image.");
    return false;
  }
  if(file.size>12*1024*1024){
    alert("The image is larger than 12 MB. Choose a smaller image.");
    return false;
  }
  selectedFile=file;$("#fileName").textContent=file.name||"Selected image";
  if(previewUrl)URL.revokeObjectURL(previewUrl);
  previewUrl=URL.createObjectURL(file);
  $("#selectedPreview").src=previewUrl;$("#selectedPreview").hidden=false;
  return true;
}
document.querySelectorAll(".mode").forEach(button=>button.addEventListener("click",()=>{
  document.querySelectorAll(".mode").forEach(item=>item.classList.remove("active"));
  button.classList.add("active");mode=button.dataset.mode;$("#modeStat").textContent=mode.toUpperCase();
}));
$("#fileInput").addEventListener("change",event=>showSelectedFile(event.target.files[0]));
$("#dropzone").addEventListener("dragover",event=>{event.preventDefault();event.currentTarget.classList.add("drag-active")});
$("#dropzone").addEventListener("dragleave",event=>event.currentTarget.classList.remove("drag-active"));
$("#dropzone").addEventListener("drop",event=>{
  event.preventDefault();event.currentTarget.classList.remove("drag-active");
  const file=event.dataTransfer.files[0];
  if(showSelectedFile(file)){
    try{const transfer=new DataTransfer();transfer.items.add(file);$("#fileInput").files=transfer.files}catch(_){}
  }
});
$("#dropzone").addEventListener("keydown",event=>{
  if(event.key==="Enter"||event.key===" "){event.preventDefault();$("#fileInput").click()}
});
document.querySelectorAll(".nav").forEach(link=>link.addEventListener("click",()=>{
  document.querySelectorAll(".nav").forEach(item=>item.classList.remove("active"));
  link.classList.add("active");
}));
async function startCapture(){
  if(isAnalyzing)return;
  let c;
  try{
    c=config();
    if(c.max<=c.min)throw Error("Maximum value must be greater than minimum value.");
    if(c.warning<c.min||c.danger>c.max)throw Error("Warning and danger thresholds must be within the instrument range.");
    if(c.danger<c.warning)throw Error("Danger threshold must be greater than or equal to warning threshold.");
  }catch(error){alert(error.message);return}
  if(!selectedFile){alert("Choose an instrument image first.");return}
  if(!api){setApiState("NOT CONFIGURED");alert("The FastAPI backend URL is not configured.");return}
  if(isAnalyzing)return;
  const btn=$("#analyzeBtn");isAnalyzing=true;btn.disabled=true;
  $("#cameraCapture").disabled=true;btn.textContent="Analyzing image…";
  try{
    const timeout=AbortSignal.timeout(120000);
    const health=await fetch(api+"/api/health",{signal:timeout});
    if(!health.ok)throw Error("Backend health check failed ("+health.status+").");
    setApiState("ONLINE");
    const fd=new FormData();
    fd.append("file",selectedFile);fd.append("mode",mode);fd.append("machine_name",c.name);fd.append("unit",c.unit);
    fd.append("min_value",c.min);fd.append("max_value",c.max);fd.append("warning_limit",c.warning);fd.append("danger_limit",c.danger);
    fd.append("start_angle",numericInput("#startAngle","Start angle"));fd.append("end_angle",numericInput("#endAngle","End angle"));
    const createdResponse=await authorizedFetch(api+"/api/jobs",{method:"POST",body:fd,signal:timeout},true);
    const created=await createdResponse.json().catch(()=>({detail:"Backend returned an unreadable response."}));
    if(!createdResponse.ok){
      if(createdResponse.status===401)setApiState("TOKEN REQUIRED");
      throw Error(created.detail||"Could not create analysis job ("+createdResponse.status+").");
    }
    jobId=created.job_id;
    const resultResponse=await authorizedFetch(api+`/api/jobs/${jobId}/start`,{method:"POST",signal:timeout},true);
    const result=await resultResponse.json().catch(()=>({detail:"Backend returned an unreadable analysis response."}));
    if(!resultResponse.ok){
      if(resultResponse.status===401)setApiState("TOKEN REQUIRED");
      throw Error(result.detail||"Image analysis failed ("+resultResponse.status+").");
    }
    const reading=result.reading;
    if(!reading||!Number.isFinite(Number(reading.value)))throw Error("The backend did not return a valid reading.");
    const analysis=reading.analysis||{};
    addReading(Number(reading.value),{
      timestamp:reading.timestamp,instrument:reading.instrument,unit:reading.unit,
      status:reading.status,mode:reading.mode,job_id:jobId,
      displayTime:new Date(reading.timestamp).toLocaleTimeString()
    });
    $("#readingTime").textContent=(mode==="digital"?"OCR estimate · ":"CV estimate · ")+now();
    await syncServerHistory();
    $("#cameraStatus").textContent=$("#cameraPanel").hidden?"Camera is off.":"Frame analyzed. Capture another frame or close the camera.";
    const message=mode==="digital"
      ?"OCR reading: "+reading.value+" "+reading.unit+"\nRecognized text: "+(analysis.raw_text||"")+
       "\nOCR score: "+(analysis.confidence??"not available")+" (not measurement accuracy)."+
       (analysis.ambiguous?"\nWARNING: OCR methods disagree. Candidate readings: "+(analysis.candidate_values||[]).join(", "):"")+
       "\nVerify the displayed value manually."
      :"Estimated reading: "+reading.value+" "+reading.unit+"\nPointer angle: "+
       (analysis.pointer_angle_deg??"not available")+"°\nConfidence: "+(analysis.confidence||"unknown")+". Verify manually.";
    alert(message);
  }catch(error){
    const isAuth=/token|unauthorized|401/i.test(error.message);
    if(isAuth)setApiState("TOKEN REQUIRED");
    else if(error.name==="AbortError"||error.name==="TimeoutError")setApiState("SLOW RESPONSE");
    else if(/fetch|network|health check|backend/i.test(error.message))setApiState("OFFLINE");
    alert("Could not analyze this image.\n"+error.message+"\n\nCheck the API connection, access token, image and calibration.");
  }finally{
    isAnalyzing=false;btn.disabled=false;$("#cameraCapture").disabled=!cameraStream;
    btn.innerHTML='Analyze instrument <span>→</span>';
  }
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
function stopAutoCapture(){
  autoCaptureRequested=false;
  if(cameraTimer){clearInterval(cameraTimer);cameraTimer=null}
  $("#cameraAutoStart").disabled=false;$("#cameraAutoStop").disabled=true;
}
function closeCamera(){
  stopAutoCapture();
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
async function startAutoCapture(){
  if(isAnalyzing)return;
  if(!cameraStream)await openCamera();
  if(!cameraStream)return;
  if(autoCaptureRequested||cameraTimer)return;
  autoCaptureRequested=true;
  $("#cameraAutoStart").disabled=true;$("#cameraAutoStop").disabled=false;
  $("#cameraStatus").textContent="Automatic capture enabled: one still frame every five seconds.";
  await captureCameraFrame();
  if(!autoCaptureRequested||!cameraStream){stopAutoCapture();return}
  cameraTimer=setInterval(()=>{
    if(autoCaptureRequested&&cameraStream&&!isAnalyzing)captureCameraFrame();
  },5000);
}
$("#cameraStart").addEventListener("click",openCamera);
$("#cameraCapture").addEventListener("click",captureCameraFrame);
$("#cameraAutoStart").addEventListener("click",startAutoCapture);
$("#cameraAutoStop").addEventListener("click",stopAutoCapture);
$("#cameraStop").addEventListener("click",closeCamera);
window.addEventListener("pagehide",closeCamera);
$("#analyzeBtn").addEventListener("click",startCapture);
$("#exportBtn").addEventListener("click",()=>{if(!history.length){alert("No readings available to export.");return}const rows=[["timestamp","instrument","reading","unit","status"],...history.map(r=>[r.time,r.name,r.value,r.unit,r.status])];const csv=rows.map(r=>r.map(v=>'"'+String(v).replace(/"/g,'""')+'"').join(",")).join("\n");const url=URL.createObjectURL(new Blob([csv],{type:"text/csv"}));const a=document.createElement("a");a.href=url;a.download="retrosense-readings.csv";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)});
async function checkApiConnection(){
  if(!api){$("#apiStatus").textContent="NOT CONFIGURED";return}
  $("#apiStatus").textContent="CONNECTING";
  try{
    const response=await fetch(api+"/api/health",{signal:AbortSignal.timeout(isLocalHost?5000:90000)});
    if(!response.ok)throw Error("Health check failed ("+response.status+")");
    const payload=await response.json();
    if(payload.status!=="ok")throw Error("Unexpected API health response");
    $("#apiStatus").textContent="ONLINE";
    if(apiToken)await syncServerHistory();
  }catch(err){
    $("#apiStatus").textContent="OFFLINE";
    console.warn("RetroSense API health check failed:",err);
  }
}
initChart();initGaugeTicks();$("#latestStat").textContent="—";$("#gaugeValue").textContent="—";$("#alertStat").textContent="WAITING";$("#alertStat").style.color="var(--muted)";$("#readingTime").textContent="No image analyzed yet";$("#updatedLabel").textContent="—";restoreDashboardState();checkApiConnection();
checkApiConnection();
