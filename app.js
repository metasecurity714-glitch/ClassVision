(() => {
  "use strict";
  const MODEL_URL = "https://justadudewhohacks.github.io/face-api.js/models";
  const DB_NAME = "classvision_db", STORE = "students";
  const $ = id => document.getElementById(id);
  const notice = $("notice"), video = $("video"), canvas = $("overlay");
  const ctx = canvas.getContext("2d");
  let db, modelsReady = false, stream = null, scanning = false, takingAttendance = false;
  let samples = [], frameTimer = null, students = [], matchStreak = new Map(), lastMarked = new Set();
  const THRESHOLD = 0.48, MARGIN = 0.08, REQUIRED_FRAMES = 4;

  function message(text, type="") { notice.textContent=text; notice.className="notice "+type; }
  function openDb() {
    return new Promise((resolve,reject)=>{
      const req=indexedDB.open(DB_NAME,1);
      req.onupgradeneeded=()=>req.result.createObjectStore(STORE,{keyPath:"rollNo"});
      req.onsuccess=()=>resolve(req.result); req.onerror=()=>reject(req.error);
    });
  }
  function allStudents() {
    return new Promise((resolve,reject)=>{
      const req=db.transaction(STORE).objectStore(STORE).getAll();
      req.onsuccess=()=>resolve(req.result||[]); req.onerror=()=>reject(req.error);
    });
  }
  function saveStudent(s) {
    return new Promise((resolve,reject)=>{
      const req=db.transaction(STORE,"readwrite").objectStore(STORE).put(s);
      req.onsuccess=resolve; req.onerror=()=>reject(req.error);
    });
  }
  function descriptorDistance(a,b) {
    let sum=0; for(let i=0;i<a.length;i++){const d=a[i]-b[i];sum+=d*d;}
    return Math.sqrt(sum);
  }
  async function refreshStudents() {
    students=await allStudents();
    $("studentCount").textContent=students.length;
    $("studentRows").innerHTML=students.length ? students.map(s=>`<tr><td>${escapeHtml(s.name)}</td><td>${escapeHtml(s.rollNo)}</td><td>${escapeHtml(s.enrolmentNo)}</td><td>${escapeHtml(s.branch)}</td><td>${s.descriptors.length}</td></tr>`).join("") : '<tr><td colspan="5" class="empty">No students registered yet.</td></tr>';
  }
  function escapeHtml(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
  async function loadModels(){
    try {
      await Promise.all([
        faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL),
        faceapi.nets.faceLandmark68Net.loadFromUri(MODEL_URL),
        faceapi.nets.faceRecognitionNet.loadFromUri(MODEL_URL)
      ]);
      modelsReady=true; $("startCamera").disabled=false; $("scanStatus").textContent="Models ready. Start camera to register or scan.";
      $("captureSample").disabled=false; message("Recognition models are ready. Connect a camera to continue.","success");
    } catch(e){console.error(e);message("Could not load face models. Check your internet connection and reload the page.","error");$("scanStatus").textContent="Model loading failed.";}
  }
  async function startCamera(){
    if(stream)return;
    try{
      stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:"user",width:{ideal:1280},height:{ideal:720}},audio:false});
      video.srcObject=stream; await video.play();
      $("videoPlaceholder").style.display="none"; $("startCamera").disabled=true; $("stopCamera").disabled=false;
      $("scanLabel").textContent="CAMERA READY"; $("scanStatus").textContent="Camera is active. Capture student samples or start attendance.";
      canvas.width=video.videoWidth;canvas.height=video.videoHeight;
      scanning=true; scanLoop();
    }catch(e){message("Camera access failed. Allow camera permission and use HTTPS or localhost.","error");console.error(e);}
  }
  function stopCamera(){
    scanning=false;takingAttendance=false; if(stream)stream.getTracks().forEach(t=>t.stop());stream=null;video.srcObject=null;
    ctx.clearRect(0,0,canvas.width,canvas.height);$("videoPlaceholder").style.display="flex";
    $("startCamera").disabled=!modelsReady;$("stopCamera").disabled=true;$("startAttendance").disabled=true;
    $("scanLabel").textContent="CAMERA OFF";$("scanStatus").textContent="Camera stopped.";
  }
  async function detectOne(){
    if(!video.videoWidth)return null;
    return faceapi.detectAllFaces(video,new faceapi.TinyFaceDetectorOptions({inputSize:416,scoreThreshold:.55})).withFaceLandmarks().withFaceDescriptors();
  }
  async function scanLoop(){
    if(!scanning)return;
    try{
      const detections=await detectOne();
      ctx.clearRect(0,0,canvas.width,canvas.height);
      for(const d of detections){
        const box=d.detection.box;
        const result=identify(d.descriptor);
        const color=result && result.distance<THRESHOLD && result.margin>MARGIN ? "#39d6a0" : result ? "#ffbf69" : "#ff727c";
        ctx.strokeStyle=color;ctx.lineWidth=3;ctx.strokeRect(box.x,box.y,box.width,box.height);
        let label=result ? (result.distance<THRESHOLD && result.margin>MARGIN ? result.student.name+" · "+result.student.rollNo : "Checking…") : "Unknown face";
        ctx.font="bold 16px sans-serif";const w=ctx.measureText(label).width+16;
        ctx.fillStyle=color;ctx.fillRect(box.x,Math.max(0,box.y-30),w,27);ctx.fillStyle="#071321";ctx.fillText(label,box.x+8,Math.max(19,box.y-11));
        if(takingAttendance && detections.length===1) await considerAttendance(result,d.descriptor);
      }
      if(detections.length>1 && takingAttendance)$("scanStatus").textContent="Multiple faces detected. Scan one student at a time.";
      else if(takingAttendance)$("scanStatus").textContent="Scanning session: "+$("sessionName").value.trim();
    }catch(e){console.error(e);}
    frameTimer=setTimeout(scanLoop,180);
  }
  function identify(descriptor){
    if(!students.length)return null;
    const ranked=students.map(student=>{
      const distances=student.descriptors.map(d=>descriptorDistance(descriptor,d));
      distances.sort((a,b)=>a-b);
      return {student,distance:distances[0]};
    }).sort((a,b)=>a.distance-b.distance);
    const first=ranked[0], second=ranked[1];
    return {...first,margin:second?second.distance-first.distance:1};
  }
  $("captureSample").addEventListener("click",async()=>{
    if(!stream){$("captureHint").textContent="Start the camera first.";return;}
    try{
      const detections=await detectOne();
      if(detections.length!==1){$("captureHint").textContent="Ensure exactly one clear face is visible.";return;}
      samples.push(Array.from(detections[0].descriptor));
      $("sampleCount").textContent=samples.length+"/5";
      $("captureHint").textContent=samples.length===5?"Five samples captured. Save the profile.":"Sample captured. Slightly change angle or expression.";
      $("saveStudent").disabled=samples.length<5;
    }catch(e){$("captureHint").textContent="Could not capture sample. Try again.";}
  });
  $("registerForm").addEventListener("submit",async e=>{
    e.preventDefault();
    if(samples.length<5)return;
    const s={name:$("studentName").value.trim(),rollNo:$("rollNo").value.trim(),enrolmentNo:$("enrolmentNo").value.trim(),branch:$("branch").value.trim(),descriptors:samples,createdAt:new Date().toISOString()};
    if(students.some(x=>x.rollNo.toLowerCase()===s.rollNo.toLowerCase())){message("That roll number is already registered.","error");return;}
    try{await saveStudent(s);samples=[];$("registerForm").reset();$("sampleCount").textContent="0/5";$("saveStudent").disabled=true;$("captureHint").textContent="Camera must be running.";await refreshStudents();message("Student registered successfully.","success");}
    catch(err){message("Could not save student data in this browser.","error");}
  });
  $("startCamera").addEventListener("click",startCamera);$("stopCamera").addEventListener("click",stopCamera);
  $("startAttendance").addEventListener("click",()=>{
    const session=$("sessionName").value.trim();
    if(!session){message("Enter a session name before starting attendance.","error");$("sessionName").focus();return;}
    if(!students.length){message("Register at least one student before taking attendance.","error");return;}
    takingAttendance=true;lastMarked=new Set();matchStreak.clear();$("scanLabel").textContent="ATTENDANCE ACTIVE";$("scanStatus").textContent="Scanning session: "+session;
    message("Attendance started for: "+session,"success");
  });
  function attendanceKey(roll,session,date){return [date,session.toLowerCase(),roll.toLowerCase()].join("|");}
  async function considerAttendance(result){
    if(!result || result.distance>=THRESHOLD || result.margin<=MARGIN){return;}
    const key=result.student.rollNo;
    matchStreak.set(key,(matchStreak.get(key)||0)+1);
    if(matchStreak.get(key)<REQUIRED_FRAMES || lastMarked.has(key))return;
    const session=$("sessionName").value.trim(), now=new Date(), date=now.toLocaleDateString("en-CA");
    const records=JSON.parse(localStorage.getItem("classvision_attendance")||"[]");
    const unique=attendanceKey(key,session,date);
    if(records.some(r=>r.uniqueKey===unique)){lastMarked.add(key);$("scanStatus").textContent=result.student.name+" already marked for this session.";return;}
    const record={name:result.student.name,rollNo:key,session,date,time:now.toLocaleTimeString(),uniqueKey:unique};
    records.unshift(record);localStorage.setItem("classvision_attendance",JSON.stringify(records));lastMarked.add(key);renderAttendance();
    $("scanStatus").textContent="Attendance marked: "+result.student.name;
  }
  function renderAttendance(){
    const records=JSON.parse(localStorage.getItem("classvision_attendance")||"[]");
    $("attendanceRows").innerHTML=records.length?records.map(r=>`<tr><td>${escapeHtml(r.name)}</td><td>${escapeHtml(r.rollNo)}</td><td>${escapeHtml(r.session)}</td><td>${escapeHtml(r.date)}</td><td>${escapeHtml(r.time)}</td><td><span style="color:#39d6a0">Present</span></td></tr>`).join(""):'<tr><td colspan="6" class="empty">No attendance records yet.</td></tr>';
  }
  function downloadCsv(name,rows){
    if(!rows.length){message("There is no data to export yet.","error");return;}
    const csv=rows.map(row=>row.map(v=>'"'+String(v??"").replace(/"/g,'""')+'"').join(",")).join("\r\n");
    const a=document.createElement("a");a.href=URL.createObjectURL(new Blob(["\ufeff"+csv],{type:"text/csv;charset=utf-8"}));a.download=name;a.click();URL.revokeObjectURL(a.href);
  }
  $("exportCsv").addEventListener("click",()=>{const r=JSON.parse(localStorage.getItem("classvision_attendance")||"[]");downloadCsv("classvision-attendance.csv",[["Name","Roll No","Session","Date","Time","Status"],...r.map(x=>[x.name,x.rollNo,x.session,x.date,x.time,"Present"])]);});
  $("exportStudents").addEventListener("click",()=>downloadCsv("classvision-students.csv",[["Name","Roll No","Enrolment No","Branch","Face Samples"],...students.map(s=>[s.name,s.rollNo,s.enrolmentNo,s.branch,s.descriptors.length])]));
  (async()=>{try{db=await openDb();await refreshStudents();renderAttendance();await loadModels();}catch(e){message("Browser storage is unavailable. Use a modern browser with IndexedDB enabled.","error");console.error(e);}})();
  window.addEventListener("beforeunload",stopCamera);
})();