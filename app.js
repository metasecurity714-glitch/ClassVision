(() => {
"use strict";
const $ = id => document.getElementById(id);
const DB_NAME = "classvision_face_db_v1";
const STORE = "records";
let db, modelsReady = false, enrollStream = null, scanStream = null;
let samples = [], enrollDescriptor = null, scanTimer = null, facing = "environment";
const streaks = new Map(), recentlyMarked = new Set();

function todayKey(){const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;}
function timeText(ts){return new Date(ts).toLocaleTimeString([], {hour:"2-digit",minute:"2-digit",second:"2-digit"});}
function openDB(){return new Promise((resolve,reject)=>{const r=indexedDB.open(DB_NAME,1);r.onupgradeneeded=()=>r.result.createObjectStore(STORE,{keyPath:"key"});r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});}
function allRecords(){return new Promise((resolve,reject)=>{const r=db.transaction(STORE).objectStore(STORE).getAll();r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});}
function putRecord(value){return new Promise((resolve,reject)=>{const r=db.transaction(STORE,"readwrite").objectStore(STORE).put(value);r.onsuccess=()=>resolve();r.onerror=()=>reject(r.error);});}
function deleteRecord(key){return new Promise((resolve,reject)=>{const r=db.transaction(STORE,"readwrite").objectStore(STORE).delete(key);r.onsuccess=()=>resolve();r.onerror=()=>reject(r.error);});}
function stopStream(stream){if(stream)stream.getTracks().forEach(t=>t.stop());}
function setMsg(id,msg){$(id).textContent=msg;}
function studentKey(id){return "student:"+id.trim().toLowerCase();}
function attendanceKey(id,date=todayKey()){return `attendance:${date}:${id.trim().toLowerCase()}`;}
async function getStudents(){return (await allRecords()).filter(x=>x.type==="student");}
async function getAttendance(){return (await allRecords()).filter(x=>x.type==="attendance");}

async function loadModels(){
  try{
    const base="https://cdn.jsdelivr.net/gh/justadudewhohacks/face-api.js@master/weights";
    await Promise.all([
      faceapi.nets.tinyFaceDetector.loadFromUri(base),
      faceapi.nets.faceLandmark68Net.loadFromUri(base),
      faceapi.nets.faceRecognitionNet.loadFromUri(base)
    ]);
    modelsReady=true;
    $("modelStatus").textContent="Models ready";
    $("modelStatus").style.background="#174b37";
    ["startEnroll","startScan"].forEach(id=>$(id).disabled=false);
    setMsg("enrollMessage","Models ready. Register consenting adults one at a time.");
  }catch(e){
    $("modelStatus").textContent="Model load failed";
    setMsg("enrollMessage","Could not load recognition models. Check internet access and reload. "+e.message);
  }
}
async function startVideo(video,facingMode){
  const stream=await navigator.mediaDevices.getUserMedia({audio:false,video:{facingMode:{ideal:facingMode},width:{ideal:1280},height:{ideal:720}}});
  video.srcObject=stream; await video.play(); return stream;
}
function descriptorFromDetection(d){return Array.from(d.descriptor);}
function averageDescriptors(arr){
  const n=arr.length, out=new Array(arr[0].length).fill(0);
  for(const a of arr)for(let i=0;i<a.length;i++)out[i]+=a[i]/n;
  return out;
}
async function captureEnrollSample(){
  const video=$("enrollVideo");
  if(!enrollStream || video.readyState<2)return;
  const d=await faceapi.detectSingleFace(video,new faceapi.TinyFaceDetectorOptions({inputSize:320,scoreThreshold:.55})).withFaceLandmarks().withFaceDescriptor();
  if(!d){setMsg("enrollMessage","No clear face detected. Face the camera with good lighting and try again.");return;}
  samples.push(descriptorFromDetection(d));
  $("sampleCount").textContent=`(${samples.length}/3)`;
  setMsg("enrollMessage",`Captured sample ${samples.length}/3. Slightly change your head angle for the next sample.`);
  if(samples.length===3){
    enrollDescriptor=averageDescriptors(samples);
    $("saveStudent").disabled=false;
    $("captureSample").disabled=true;
    setMsg("enrollMessage","Three samples captured. Save the student profile.");
  }
}
async function saveStudent(){
  const name=$("studentName").value.trim(), id=$("studentId").value.trim();
  if(!name||!id||!enrollDescriptor||!$("consent").checked){setMsg("enrollMessage","Enter name and ID, capture 3 samples, and confirm consent.");return;}
  const key=studentKey(id);
  if((await allRecords()).some(r=>r.key===key)){setMsg("enrollMessage","That student ID is already registered.");return;}
  await putRecord({key,type:"student",name,id,descriptor:enrollDescriptor,createdAt:Date.now()});
  samples=[];enrollDescriptor=null;
  $("sampleCount").textContent="(0/3)";$("studentName").value="";$("studentId").value="";$("consent").checked=false;
  $("saveStudent").disabled=true;$("captureSample").disabled=false;
  setMsg("enrollMessage",`${name} registered on this device.`);
  await renderAll();
}
async function startEnroll(){
  try{
    if(!navigator.mediaDevices?.getUserMedia)throw new Error("Camera access is unavailable. Open the GitHub Pages HTTPS URL in Chrome.");
    samples=[];enrollDescriptor=null;$("sampleCount").textContent="(0/3)";
    enrollStream=await startVideo($("enrollVideo"),"user");
    $("captureSample").disabled=false;$("stopEnroll").disabled=false;
    setMsg("enrollMessage","Camera ready. Capture 3 samples of this consenting adult.");
  }catch(e){setMsg("enrollMessage",e.message);}
}
function stopEnroll(){stopStream(enrollStream);enrollStream=null;$("enrollVideo").srcObject=null;$("captureSample").disabled=true;$("stopEnroll").disabled=true;}
function distance(a,b){let sum=0;for(let i=0;i<a.length;i++){const d=a[i]-b[i];sum+=d*d;}return Math.sqrt(sum);}
async function bestMatch(descriptor,students){
  const ranked=students.map(s=>({student:s,d:distance(descriptor,s.descriptor)})).sort((a,b)=>a.d-b.d);
  if(!ranked.length)return null;
  const first=ranked[0], second=ranked[1];
  // Conservative gate: require a strong match and separation from the runner-up.
  if(first.d>0.46 || (second && second.d-first.d<0.08))return {uncertain:true,distance:first.d};
  return {student:first.student,distance:first.d};
}
async function markAttendance(student){
  const key=attendanceKey(student.id);
  if(recentlyMarked.has(key))return false;
  const existing=await dbGet(key);
  if(existing)return false;
  const rec={key,type:"attendance",studentId:student.id,studentName:student.name,date:todayKey(),timestamp:Date.now(),method:"face-match"};
  await putRecord(rec);recentlyMarked.add(key);
  addEvent(`Marked present: ${student.name} (${student.id}) · ${timeText(rec.timestamp)}`);
  await renderAttendance();
  return true;
}
function dbGet(key){return new Promise((resolve,reject)=>{const r=db.transaction(STORE).objectStore(STORE).get(key);r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});}
function addEvent(msg){const el=document.createElement("div");el.className="event";el.textContent=msg;$("scanEvents").prepend(el);while($("scanEvents").children.length>8)$("scanEvents").lastChild.remove();}
async function scanFrame(){
  if(!scanStream||$("scanVideo").readyState<2)return;
  const video=$("scanVideo"), canvas=$("overlay");
  const size={width:video.videoWidth,height:video.videoHeight};
  if(!size.width)return;
  canvas.width=size.width;canvas.height=size.height;
  const detections=await faceapi.detectAllFaces(video,new faceapi.TinyFaceDetectorOptions({inputSize:416,scoreThreshold:.6})).withFaceLandmarks().withFaceDescriptors();
  const ctx=canvas.getContext("2d");ctx.clearRect(0,0,canvas.width,canvas.height);
  const students=await getStudents();
  for(let i=0;i<detections.length;i++){
    const det=detections[i], box=det.detection.box;
    ctx.strokeStyle="#40e0a0";ctx.lineWidth=3;ctx.strokeRect(box.x,box.y,box.width,box.height);
    const result=await bestMatch(descriptorFromDetection(det),students);
    if(!result||result.uncertain){
      ctx.fillStyle="#ffd166";ctx.font="18px sans-serif";ctx.fillText("Unverified",box.x,Math.max(22,box.y-8));
      continue;
    }
    const s=result.student, key=s.id.toLowerCase();
    const count=(streaks.get(key)||0)+1;streaks.set(key,count);
    ctx.fillStyle="#40e0a0";ctx.font="18px sans-serif";ctx.fillText(s.name,box.x,Math.max(22,box.y-8));
    if(count>=3){const did=await markAttendance(s);if(did)streaks.set(key,0);}
  }
  // Remove stale streaks when a face disappears from the frame.
  const active=new Set();
  for(const d of detections){const r=await bestMatch(descriptorFromDetection(d),students);if(r&&!r.uncertain)active.add(r.student.id.toLowerCase());}
  for(const k of [...streaks.keys()])if(!active.has(k))streaks.delete(k);
}
async function startScan(){
  try{
    if(!(await getStudents()).length){setMsg("scanMessage","Register at least one consenting adult first.");return;}
    scanStream=await startVideo($("scanVideo"),facing);
    $("startScan").disabled=true;$("stopScan").disabled=false;$("switchCamera").disabled=false;
    setMsg("scanMessage","Scanning. Keep faces visible and well lit. Ambiguous matches will not be marked.");
    scanTimer=setInterval(()=>scanFrame().catch(e=>setMsg("scanMessage","Scanner error: "+e.message)),850);
  }catch(e){setMsg("scanMessage",e.message);}
}
function stopScan(){
  if(scanTimer)clearInterval(scanTimer);scanTimer=null;
  stopStream(scanStream);scanStream=null;$("scanVideo").srcObject=null;
  $("startScan").disabled=false;$("stopScan").disabled=true;$("switchCamera").disabled=true;
  streaks.clear();setMsg("scanMessage","Scanner stopped.");
  const c=$("overlay").getContext("2d");c.clearRect(0,0,$("overlay").width,$("overlay").height);
}
async function switchCamera(){facing=facing==="environment"?"user":"environment";$("cameraFacing").value=facing;stopScan();await startScan();}
async function renderStudents(){
  const students=await getStudents();$("studentTotal").textContent=students.length;
  const root=$("studentList");root.replaceChildren();
  for(const s of students){
    const row=document.createElement("div");row.className="student";
    const info=document.createElement("span");info.textContent=`${s.name} · ${s.id}`;
    const del=document.createElement("button");del.className="danger";del.textContent="Delete";
    del.onclick=async()=>{if(confirm(`Delete ${s.name} and their stored face descriptor?`)){await deleteRecord(s.key);await renderAll();}};
    row.append(info,del);root.append(row);
  }
}
async function renderAttendance(){
  const records=(await getAttendance()).filter(r=>r.date===todayKey()).sort((a,b)=>b.timestamp-a.timestamp);
  const body=$("attendanceRows");body.replaceChildren();
  for(const r of records){const tr=document.createElement("tr");[timeText(r.timestamp),r.studentName,r.studentId,"Present"].forEach(v=>{const td=document.createElement("td");td.textContent=v;tr.append(td);});body.append(tr);}
}
async function renderAll(){await renderStudents();await renderAttendance();}
function csvEscape(v){return '"'+String(v??"").replace(/"/g,'""')+'"';}
async function exportCsv(all=false){
  const records=(await getAttendance()).filter(r=>all||r.date===todayKey()).sort((a,b)=>a.timestamp-b.timestamp);
  const rows=[["Date","Time","Student","Student ID","Status"],...records.map(r=>[r.date,timeText(r.timestamp),r.studentName,r.studentId,"Present"])];
  const blob=new Blob([rows.map(row=>row.map(csvEscape).join(",")).join("\r\n")],{type:"text/csv;charset=utf-8"});
  const url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;a.download=all?"classvision-all-attendance.csv":`classvision-${todayKey()}.csv`;a.click();URL.revokeObjectURL(url);
}
async function clearToday(){if(!confirm("Delete today's attendance records?"))return;for(const r of await getAttendance())if(r.date===todayKey())await deleteRecord(r.key);await renderAttendance();}
async function clearData(){if(!confirm("Permanently delete all registered students, face descriptors and attendance records from this browser?"))return;for(const r of await allRecords())await deleteRecord(r.key);recentlyMarked.clear();await renderAll();setMsg("enrollMessage","All local data cleared.");}

async function init(){
  try{db=await openDB();await renderAll();}catch(e){setMsg("enrollMessage","Local database error: "+e.message);}
  $("startEnroll").onclick=startEnroll;$("captureSample").onclick=captureEnrollSample;$("saveStudent").onclick=saveStudent;$("stopEnroll").onclick=stopEnroll;
  $("startScan").onclick=startScan;$("stopScan").onclick=stopScan;$("switchCamera").onclick=switchCamera;
  $("cameraFacing").onchange=e=>{facing=e.target.value;if(scanStream)switchCamera();};
  $("exportCsv").onclick=()=>exportCsv(false);$("exportAll").onclick=()=>exportCsv(true);$("clearToday").onclick=clearToday;$("clearData").onclick=clearData;
  if(!window.isSecureContext)setMsg("enrollMessage","Open the published GitHub Pages HTTPS address. Camera access will not work on an insecure page.");
  if(window.faceapi)loadModels();else setMsg("enrollMessage","Recognition library did not load. Check internet and reload.");
}
window.addEventListener("DOMContentLoaded",init);
})();