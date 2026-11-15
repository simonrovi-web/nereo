/* ═══════════════════════════════════════════════════════════════
   NEREO · visor de fenómenos anómalos aéreos y submarinos
   Datos: NUFORC (reportes geocodificados por ciudad, 1906–2014)
   ═══════════════════════════════════════════════════════════════ */
(() => {
"use strict";
const $ = s => document.querySelector(s);
const fmt = n => (n ?? 0).toLocaleString("es-CL");
const clamp = (v,a,b) => v < a ? a : v > b ? b : v;

/* ───────────── categorías ───────────── */
const CAT = [
  {k:"aereo",      n:"AÉREO · SIN AGUA",     c:"#3f86aa", d:"Reporte sin elementos acuáticos."},
  {k:"costero",    n:"COSTERO",              c:"#34dfe8", d:"A menos de 20 km de la línea de costa."},
  {k:"embarcacion",n:"DESDE EMBARCACIÓN",    c:"#9d7bff", d:"Observado desde un barco o plataforma."},
  {k:"agua",       n:"SOBRE EL AGUA",        c:"#5ef2a8", d:"Coordenada en el mar o relato sobre agua."},
  {k:"entro",      n:"ENTRÓ AL AGUA",        c:"#ffb340", d:"El objeto se sumergió."},
  {k:"emergio",    n:"EMERGIÓ DEL AGUA",     c:"#ff5a52", d:"El objeto salió del agua."},
];
const RARE = 2; // mar >= 2 se considera caso destacado

/* ───────────── estado ───────────── */
const S = {
  d:null, world:null, st:null, N:0, vids:[], cams:[],
  view:{z:1.6, cx:-40, cy:28},
  L:{aereo:1,costero:1,embarcacion:1,agua:1,entro:1,emergio:1,
     evVideo:0,evFoto:0,evRadar:0,evMulti:0,casos:1,camaras:0,envios:1,ultimos:1,
     xMet:0,xFuego:0,xLanz:0,puertos:0,bati:1,rutas:0,naval:0,
     calor:0,densidad:0,pulso:1,
     tierra:1,lagos:1,fronteras:1,reticula:1,terminador:1,oceano:1,
     scan:1,leyenda:1,ticker:1},
  F:{y0:1906,y1:2023,shapes:new Set(),hour:-1,dur:0,coast:-1,soloAgua:0,sol:0,sinExp:0},
  sel:-1, play:0, dirty:1, panel:null, catIdx:[], counts:[]
};

/* ───────────── carga ───────────── */
const boot = $("#boot"), bootBar = $("#bootBar"), bootLog = $("#bootLog");
const log = (t,p) => { bootLog.textContent = t; bootBar.style.width = p + "%"; };

function dec(b64, T){
  const bin = atob(b64), len = bin.length, u = new Uint8Array(len);
  for (let i=0;i<len;i++) u[i] = bin.charCodeAt(i);
  return new T(u.buffer);
}

async function load(){
  try{
    log("ENLAZANDO CARTOGRAFÍA…", 12);
    const world = await (await fetch("data/world.json")).json();
    log("DESCIFRANDO REGISTROS…", 45);
    const raw = await (await fetch("data/points.json")).json();
    log("CALIBRANDO ESTADÍSTICA…", 72);
    const st = await (await fetch("data/stats.json")).json();
    log("ABRIENDO EXPEDIENTES AUDIOVISUALES…", 88);
    const vids = await (await fetch("data/videos.json")).json();
    const cams = await (await fetch("data/cams.json")).json();
    S.vids = vids.casos; S.vidNota = vids.nota;
    S.cams = cams.sitios; S.camNota = cams.nota;
    try { S.marx = await (await fetch("data/mar.json")).json(); } catch(e){ S.marx = null; }

    S.world = world; S.st = st; S.N = raw.n;
    S.d = {
      lat: dec(raw.lat, Int32Array), lon: dec(raw.lon, Int32Array),
      year: dec(raw.year, Uint16Array), month: dec(raw.month, Uint8Array),
      hour: dec(raw.hour, Uint8Array), shape: dec(raw.shape, Uint8Array),
      mar: dec(raw.mar, Uint8Array), flags: dec(raw.flags, Uint8Array),
      dur: dec(raw.dur, Uint16Array), dcoast: dec(raw.dcoast, Uint16Array),
      place: dec(raw.place, Uint16Array), ev: dec(raw.ev, Uint8Array),
      day: dec(raw.day, Uint8Array), exp: dec(raw.exp, Uint8Array), sol: dec(raw.sol, Uint8Array), y1: raw.y1,
      places: raw.places, shapes: raw.shapes,
    };
    log("NÚCLEO EN LÍNEA", 100);
    setTimeout(start, 240);
  }catch(e){
    bootLog.innerHTML = "ERROR DE ENLACE CON EL BANCO DE DATOS<br><span style='color:#ff5a52'>"+e.message+"</span>";
  }
}

/* ───────────── proyección mercator ───────────── */
const cv = $("#map"), ctx = cv.getContext("2d", {alpha:false});
const base = document.createElement("canvas"), bctx = base.getContext("2d", {alpha:false});
let W=0, H=0, DPR=1, ox=0, oy=0;

const sc = () => 256 * Math.pow(2, S.view.z);
const lon2x = l => (l+180)/360 * sc();
const lat2y = l => { const s = Math.sin(clamp(l,-85.05,85.05)*Math.PI/180);
  return (0.5 - Math.log((1+s)/(1-s))/(4*Math.PI)) * sc(); };
const x2lon = x => x/sc()*360 - 180;
const y2lat = y => 180/Math.PI*Math.atan(Math.sinh(Math.PI*(1-2*y/sc())));
const px = l => lon2x(l) - ox, py = l => lat2y(l) - oy;

function fitOrigin(){ ox = lon2x(S.view.cx) - W/2; oy = lat2y(S.view.cy) - H/2; }

function resize(){
  DPR = Math.min(window.devicePixelRatio||1, 2);
  W = cv.clientWidth; H = cv.clientHeight;
  for (const c of [cv, base]) { c.width = W*DPR; c.height = H*DPR; }
  ctx.setTransform(DPR,0,0,DPR,0,0); bctx.setTransform(DPR,0,0,DPR,0,0);
  S.dirty = 1;
}

/* ───────────── filtros ───────────── */
function pass(i){
  const d = S.d, m = d.mar[i];
  if (!S.L[CAT[m].k]) return false;
  const y = d.year[i]; if (y < S.F.y0 || y > S.F.y1) return false;
  if (S.F.shapes.size && !S.F.shapes.has(d.shape[i])) return false;
  if (S.F.hour >= 0){ const h = d.hour[i]; if (h > 23) return false;
    const band = S.F.hour; // 0 noche 1 amanecer 2 día 3 atardecer
    const ok = band===0 ? (h>=22||h<5) : band===1 ? (h>=5&&h<9) : band===2 ? (h>=9&&h<17) : (h>=17&&h<22);
    if (!ok) return false; }
  if (S.F.dur > 0 && d.dur[i] < S.F.dur) return false;
  if (S.F.coast >= 0 && d.dcoast[i] > S.F.coast) return false;
  if (S.F.soloAgua && !(d.flags[i] & 32)) return false;
  if (S.F.sol && d.sol[i] < S.F.sol) return false;
  if (S.F.sinExp && d.exp[i]) return false;
  return true;
}

/* ───────────── dibujo base ───────────── */
function drawRings(c, rings, fill, stroke, lw){
  c.beginPath();
  const sp = sc();
  for (const r of rings){
    let started = false, lastX = 0;
    for (let i=0;i<r.length;i++){
      const x = px(r[i][0]), y = py(r[i][1]);
      if (!started){ c.moveTo(x,y); started = true; } else c.lineTo(x,y);
      lastX = x;
    }
    c.closePath();
    // repetición horizontal para que el mundo se vea continuo
    if (sp < W*2.2){
      for (const off of [-sp, sp]){
        let st2 = false;
        for (let i=0;i<r.length;i++){
          const x = px(r[i][0]) + off, y = py(r[i][1]);
          if (!st2){ c.moveTo(x,y); st2 = true; } else c.lineTo(x,y);
        }
        c.closePath();
      }
    }
  }
  if (fill){ c.fillStyle = fill; c.fill("evenodd"); }
  if (stroke){ c.strokeStyle = stroke; c.lineWidth = lw||1; c.stroke(); }
}

function drawLines(c, lines, stroke, lw){
  c.beginPath();
  for (const l of lines){
    for (let i=0;i<l.length;i++){
      const x = px(l[i][0]), y = py(l[i][1]);
      i ? c.lineTo(x,y) : c.moveTo(x,y);
    }
  }
  c.strokeStyle = stroke; c.lineWidth = lw||.6; c.stroke();
}

function drawGraticule(c){
  c.beginPath(); c.strokeStyle = "rgba(120,190,210,.07)"; c.lineWidth = .5;
  const step = S.view.z < 2 ? 20 : S.view.z < 4 ? 10 : S.view.z < 6 ? 5 : 1;
  for (let lo=-180; lo<=180; lo+=step){ const x = px(lo); if (x<-50||x>W+50) continue; c.moveTo(x,0); c.lineTo(x,H); }
  for (let la=-80; la<=80; la+=step){ const y = py(la); if (y<-50||y>H+50) continue; c.moveTo(0,y); c.lineTo(W,y); }
  c.stroke();
  // ecuador y trópicos
  c.beginPath(); c.strokeStyle = "rgba(52,223,232,.16)"; c.lineWidth = .7;
  c.moveTo(0,py(0)); c.lineTo(W,py(0)); c.stroke();
  c.beginPath(); c.strokeStyle = "rgba(52,223,232,.08)"; c.setLineDash([3,5]);
  for (const la of [23.44,-23.44]){ c.moveTo(0,py(la)); c.lineTo(W,py(la)); }
  c.stroke(); c.setLineDash([]);
}

function subsolar(){
  const now = new Date();
  const d = (now - Date.UTC(now.getUTCFullYear(),0,0)) / 864e5;
  const g = 2*Math.PI/365.24 * (d - 1 + (now.getUTCHours()-12)/24);
  const decl = 0.006918 - 0.399912*Math.cos(g) + 0.070257*Math.sin(g)
             - 0.006758*Math.cos(2*g) + 0.000907*Math.sin(2*g)
             - 0.002697*Math.cos(3*g) + 0.00148*Math.sin(3*g);
  const utc = now.getUTCHours() + now.getUTCMinutes()/60 + now.getUTCSeconds()/3600;
  return {lat: decl*180/Math.PI, lon: 180 - utc*15};
}

function drawTerminator(c){
  const s = subsolar(), dec = s.lat*Math.PI/180;
  if (Math.abs(dec) < 0.003) return;
  const pts = [];
  for (let lo=-180; lo<=180; lo+=1.5){
    const h = (lo - s.lon)*Math.PI/180;
    let la = Math.atan(-Math.cos(h)/Math.tan(dec))*180/Math.PI;
    pts.push([lo, clamp(la,-85,85)]);
  }
  const north = dec < 0; // si el sol está al sur, la noche cubre el norte
  c.save(); c.beginPath();
  pts.forEach((p,i)=> i ? c.lineTo(px(p[0]),py(p[1])) : c.moveTo(px(p[0]),py(p[1])));
  c.lineTo(px(180), north ? -9e3 : 9e3); c.lineTo(px(-180), north ? -9e3 : 9e3); c.closePath();
  c.fillStyle = "rgba(0,3,8,.58)"; c.fill();
  c.strokeStyle = "rgba(255,179,64,.22)"; c.lineWidth = .8;
  c.beginPath(); pts.forEach((p,i)=> i ? c.lineTo(px(p[0]),py(p[1])) : c.moveTo(px(p[0]),py(p[1])));
  c.stroke(); c.restore();
}

/* ───────────── capas de datos ───────────── */
function drawPoints(c){
  const d = S.d, z = S.view.z;
  const r = z < 2 ? 1.1 : z < 4 ? 1.6 : z < 6 ? 2.3 : 3.2;
  c.globalCompositeOperation = z < 4.2 ? "lighter" : "source-over";
  for (let ci = 0; ci < CAT.length; ci++){
    if (!S.L[CAT[ci].k]) continue;
    const idx = S.catIdx[ci]; if (!idx) continue;
    c.fillStyle = CAT[ci].c;
    c.globalAlpha = ci === 0 ? (z < 3 ? .42 : .62) : .92;
    for (let k = 0; k < idx.length; k++){
      const i = idx[k];
      if (!pass(i)) continue;
      const x = px(d.lon[i]/1e4), y = py(d.lat[i]/1e4);
      if (x < -20 || x > W+20 || y < -20 || y > H+20) continue;
      c.fillRect(x-r/2, y-r/2, r, r);
    }
  }
  c.globalAlpha = 1; c.globalCompositeOperation = "source-over";
}

function drawHeat(c){
  const d = S.d, cell = 7, gw = Math.ceil(W/cell), gh = Math.ceil(H/cell);
  const g = new Float32Array(gw*gh); let max = 0;
  for (let i=0;i<S.N;i++){
    if (!pass(i)) continue;
    const x = px(d.lon[i]/1e4), y = py(d.lat[i]/1e4);
    if (x<0||x>=W||y<0||y>=H) continue;
    const k = (y/cell|0)*gw + (x/cell|0); g[k] += 1;
  }
  // difuminado separable
  const t = new Float32Array(gw*gh);
  for (let y=0;y<gh;y++) for (let x=0;x<gw;x++){
    let s=0,n=0; for (let k=-2;k<=2;k++){ const xx=x+k; if (xx<0||xx>=gw) continue; s+=g[y*gw+xx]*(3-Math.abs(k)); n+=3-Math.abs(k); }
    t[y*gw+x] = s/n;
  }
  for (let x=0;x<gw;x++) for (let y=0;y<gh;y++){
    let s=0,n=0; for (let k=-2;k<=2;k++){ const yy=y+k; if (yy<0||yy>=gh) continue; s+=t[yy*gw+x]*(3-Math.abs(k)); n+=3-Math.abs(k); }
    g[y*gw+x] = s/n; if (g[y*gw+x] > max) max = g[y*gw+x];
  }
  if (max <= 0) return;
  const stops = [[0,8,28,0],[.18,14,96,120],[.42,52,223,232],[.68,94,242,168],[.86,255,179,64],[1,255,90,82]];
  const col = v => { for (let i=1;i<stops.length;i++){ if (v<=stops[i][0]){ const a=stops[i-1],b=stops[i],t=(v-a[0])/(b[0]-a[0]);
      return [a[1]+(b[1]-a[1])*t, a[2]+(b[2]-a[2])*t, a[3]+(b[3]-a[3])*t]; } } return [255,90,82]; };
  const off = document.createElement("canvas"); off.width = gw; off.height = gh;
  const octx = off.getContext("2d"), img = octx.createImageData(gw,gh), px4 = img.data;
  for (let i=0;i<gw*gh;i++){
    const v = Math.pow(g[i]/max, .42);
    if (v < .02) continue;
    const [r,gg,b] = col(v);
    px4[i*4]=r; px4[i*4+1]=gg; px4[i*4+2]=b; px4[i*4+3] = Math.min(235, v*300);
  }
  octx.putImageData(img,0,0);
  c.save(); c.globalCompositeOperation = "lighter"; c.imageSmoothingEnabled = true;
  c.globalAlpha = .9; c.drawImage(off, 0, 0, W, H); c.restore();
}

function drawDensity(c){
  const d = S.d, cell = 26, gw = Math.ceil(W/cell)+1, gh = Math.ceil(H/cell)+1;
  const g = new Uint32Array(gw*gh); let max = 0;
  for (let i=0;i<S.N;i++){
    if (!pass(i)) continue;
    const x = px(d.lon[i]/1e4), y = py(d.lat[i]/1e4);
    if (x<0||x>=W||y<0||y>=H) continue;
    const k = (y/cell|0)*gw + (x/cell|0); if (++g[k] > max) max = g[k];
  }
  if (!max) return;
  c.save(); c.lineWidth = .5;
  for (let y=0;y<gh;y++) for (let x=0;x<gw;x++){
    const v = g[y*gw+x]; if (!v) continue;
    const t = Math.pow(v/max, .4);
    c.fillStyle = `rgba(52,223,232,${t*.17})`;
    c.fillRect(x*cell, y*cell, cell-1, cell-1);
    if (t > .55){ c.strokeStyle = `rgba(52,223,232,${t*.5})`; c.strokeRect(x*cell+.5, y*cell+.5, cell-2, cell-2);
      if (t > .78 && cell > 20){ c.fillStyle = "rgba(210,245,250,.75)"; c.font = "8px ui-monospace,monospace";
        c.fillText(v, x*cell+3, y*cell+11); } }
  }
  c.restore();
}

const EV = [
  {k:"evVideo", bit:1, c:"#ffb340", n:"RELATO CON VIDEO"},
  {k:"evFoto",  bit:2, c:"#34dfe8", n:"RELATO CON FOTOS"},
  {k:"evRadar", bit:4, c:"#9d7bff", n:"CONFIRMACIÓN POR RADAR"},
  {k:"evMulti", bit:8, c:"#5ef2a8", n:"MÚLTIPLES TESTIGOS"},
];
function drawEvidence(c){
  const d = S.d;
  for (const e of EV){
    if (!S.L[e.k]) continue;
    c.strokeStyle = e.c; c.lineWidth = 1; c.globalAlpha = .85;
    c.beginPath();
    for (let i=0;i<S.N;i++){
      if (!(d.ev[i] & e.bit)) continue;
      if (!pass(i)) continue;
      const x = px(d.lon[i]/1e4), y = py(d.lat[i]/1e4);
      if (x<-10||x>W+10||y<-10||y>H+10) continue;
      c.moveTo(x+4, y); c.arc(x, y, 4, 0, 6.284);
    }
    c.stroke(); c.globalAlpha = 1;
  }
}

function markerPos(o){ return [px(o.lon), py(o.lat)]; }

function drawCases(c, t){
  if (!S.L.casos) return;
  const ph = (Math.sin(t/900)+1)/2;
  S.vids.forEach((v, vi) => {
    const [x,y] = markerPos(v);
    if (x<-40||x>W+40||y<-40||y>H+40) return;
    const col = v.agua ? "#ffb340" : "#34dfe8";
    c.strokeStyle = col; c.fillStyle = col; c.lineWidth = 1.2;
    c.globalAlpha = .35 + ph*.3;
    c.beginPath(); c.arc(x, y, 13 + ph*4, 0, 6.284); c.stroke();
    c.globalAlpha = 1;
    c.beginPath(); c.arc(x, y, 7, 0, 6.284); c.stroke();
    // triángulo de reproducción
    c.beginPath(); c.moveTo(x-2.2,y-3.4); c.lineTo(x+3.6,y); c.lineTo(x-2.2,y+3.4); c.closePath(); c.fill();
    if (S.view.z > 2.4){
      c.font = "8px ui-monospace,monospace"; c.fillStyle = col; c.globalAlpha = .85;
      c.fillText(v.titulo.toUpperCase().slice(0,34), x+17, y+3 + (vi%2 ? 11 : -6)); c.globalAlpha = 1;
    }
  });
}

function drawCams(c){
  if (!S.L.camaras) return;
  for (const s of S.cams){
    const [x,y] = markerPos(s);
    if (x<-40||x>W+40||y<-40||y>H+40) continue;
    c.strokeStyle = "#5ef2a8"; c.lineWidth = 1; c.globalAlpha = .9;
    c.beginPath(); c.arc(x, y, 5.5, 0, 6.284); c.stroke();
    c.beginPath();
    c.moveTo(x-9,y); c.lineTo(x-6.5,y); c.moveTo(x+6.5,y); c.lineTo(x+9,y);
    c.moveTo(x,y-9); c.lineTo(x,y-6.5); c.moveTo(x,y+6.5); c.lineTo(x,y+9);
    c.stroke();
    if (S.view.z > 3){
      c.font = "8px ui-monospace,monospace"; c.fillStyle = "#5ef2a8"; c.globalAlpha = .8;
      c.fillText(s.n.toUpperCase(), x+13, y+3);
    }
    c.globalAlpha = 1;
  }
}

function renderBase(){
  fitOrigin();
  bctx.fillStyle = "#04070c"; bctx.fillRect(0,0,W,H);
  if (S.L.oceano){
    const g = bctx.createLinearGradient(0,0,0,H);
    g.addColorStop(0,"#05090f"); g.addColorStop(.5,"#061019"); g.addColorStop(1,"#04070c");
    bctx.fillStyle = g; bctx.fillRect(0,0,W,H);
  }
  if (S.L.bati) drawBati(bctx);
  if (S.L.reticula) drawGraticule(bctx);
  if (S.L.rutas) drawRutas(bctx);
  if (S.L.tierra) drawRings(bctx, S.world.land, "#0e1c29", "rgba(80,205,225,.42)", .85);
  if (S.L.lagos)  drawRings(bctx, S.world.lakes, "#061019", "rgba(70,190,210,.26)", .5);
  if (S.L.fronteras) drawLines(bctx, S.world.borders, "rgba(120,190,210,.13)", .5);
  if (S.L.terminador) drawTerminator(bctx);
  if (S.L.calor) drawHeat(bctx);
  if (S.L.densidad) drawDensity(bctx);
  drawPoints(bctx);
  drawEvidence(bctx);
  drawExpl(bctx);
  if (S.L.naval) drawNaval(bctx);
  if (S.L.puertos) drawPuertos(bctx);
  S.dirty = 0;
}

/* ───────────── superposición animada ───────────── */
function renderOverlay(t){
  ctx.drawImage(base, 0, 0, W, H);
  const d = S.d;
  if (S.L.pulso){
    const ph = (Math.sin(t/620)+1)/2;
    for (let ci = 4; ci < CAT.length; ci++){
      if (!S.L[CAT[ci].k]) continue;
      const idx = S.catIdx[ci]; if (!idx) continue;
      ctx.strokeStyle = CAT[ci].c; ctx.lineWidth = 1;
      for (let k=0;k<idx.length;k++){
        const i = idx[k]; if (!pass(i)) continue;
        const x = px(d.lon[i]/1e4), y = py(d.lat[i]/1e4);
        if (x<-30||x>W+30||y<-30||y>H+30) continue;
        const r = 4 + ph*6;
        ctx.globalAlpha = .55*(1-ph);
        ctx.beginPath(); ctx.arc(x,y,r,0,6.284); ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;
  }
  drawZonas(ctx);
  drawUltimos(ctx, t);
  drawEnvios(ctx);
  drawCams(ctx);
  drawCases(ctx, t);
  if (S.sel >= 0){
    const i = S.sel, x = px(d.lon[i]/1e4), y = py(d.lat[i]/1e4);
    ctx.strokeStyle = "#eafaff"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.arc(x,y,11,0,6.284); ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(x-19,y); ctx.lineTo(x-13,y); ctx.moveTo(x+13,y); ctx.lineTo(x+19,y);
    ctx.moveTo(x,y-19); ctx.lineTo(x,y-13); ctx.moveTo(x,y+13); ctx.lineTo(x,y+19);
    ctx.stroke();
  }
}

let raf = 0;
function loop(t){
  if (S.dirty) renderBase();
  renderOverlay(t);
  raf = requestAnimationFrame(loop);
}
const mark = () => { S.dirty = 1; };

/* ───────────── interacción del mapa ───────────── */
let drag = null;
cv.addEventListener("mousedown", e => { drag = {x:e.clientX, y:e.clientY, cx:S.view.cx, cy:S.view.cy, moved:0}; cv.classList.add("drag"); });
window.addEventListener("mouseup", e => {
  if (drag && !drag.moved) pick(e.offsetX ?? e.clientX, e.clientY - cv.getBoundingClientRect().top);
  drag = null; cv.classList.remove("drag");
});
window.addEventListener("mousemove", e => {
  const rect = cv.getBoundingClientRect(), mx = e.clientX - rect.left, my = e.clientY - rect.top;
  if (drag){
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = 1;
    const s = sc();
    S.view.cx = ((drag.cx + 180 - dx/s*360 + 540) % 360) - 180;
    const y0 = lat2y(drag.cy) - dy;
    S.view.cy = clamp(y2lat(y0), -82, 82);
    mark();
  }
  if (mx>=0 && my>=0 && mx<=W && my<=H){
    const lo = ((x2lon(mx+ox)+540)%360)-180, la = y2lat(my+oy);
    $("#sbCursor").textContent = `LAT ${la.toFixed(3)}  LON ${lo.toFixed(3)}`;
  }
});
cv.addEventListener("wheel", e => {
  e.preventDefault();
  const rect = cv.getBoundingClientRect(), mx = e.clientX-rect.left, my = e.clientY-rect.top;
  const lo = x2lon(mx+ox), la = y2lat(my+oy);
  S.view.z = clamp(S.view.z - e.deltaY*0.0022, .6, 11);
  fitOrigin();
  const lo2 = x2lon(mx+ox), la2 = y2lat(my+oy);
  S.view.cx = clamp(S.view.cx + (lo-lo2), -180, 180);
  S.view.cy = clamp(S.view.cy + (la-la2), -82, 82);
  mark(); hud();
}, {passive:false});

function zoomBy(d){ S.view.z = clamp(S.view.z + d, .6, 11); mark(); hud(); }
function flyTo(lon, lat, z){
  const from = {...S.view}, to = {cx:lon, cy:clamp(lat,-82,82), z: z ?? Math.max(S.view.z, 6)};
  const t0 = performance.now(), dur = 620;
  (function step(t){
    const k = clamp((t-t0)/dur, 0, 1), e = k<.5 ? 2*k*k : 1-Math.pow(-2*k+2,2)/2;
    S.view.cx = from.cx + (to.cx-from.cx)*e;
    S.view.cy = from.cy + (to.cy-from.cy)*e;
    S.view.z  = from.z  + (to.z -from.z )*e;
    mark(); hud();
    if (k < 1) requestAnimationFrame(step);
  })(t0);
}

function pick(mx, my){
  if (S.pickMode && S.pickMode.zona){
    const lo = ((x2lon(mx+ox)+540)%360)-180, la = y2lat(my+oy), z = S.pickMode.zona;
    S.pickMode = 0;
    guardarZonas([...S.zonas, {n:z.n, km:z.km, lat:+la.toFixed(3), lon:+lo.toFixed(3)}]);
    return;
  }
  if (S.pickMode){
    const lo = ((x2lon(mx+ox)+540)%360)-180, la = y2lat(my+oy);
    S.pickMode = 0;
    S.form.lat = la.toFixed(4); S.form.lon = lo.toFixed(4);
    const a = $("#fLat"), b = $("#fLon");
    if (a && b){ a.value = S.form.lat; b.value = S.form.lon; }
    toast("COORDENADA FIJADA · " + S.form.lat + ", " + S.form.lon);
    return;
  }
  if (S.L.ultimos) for (const u of S.ult){
    if (typeof u.lat !== "number") continue;
    const x = px(u.lon), y = py(u.lat);
    if ((x-mx)**2 + (y-my)**2 < 220){ S.sel = -1; dossierUlt(u); return; }
  }
  if (S.L.envios) for (const e of S.env){
    const x = px(e.lon), y = py(e.lat);
    if ((x-mx)**2 + (y-my)**2 < 170){ S.sel = -1; dossierEnv(e); return; }
  }
  if (S.L.casos) for (const v of S.vids){
    const [x,y] = markerPos(v);
    if ((x-mx)**2 + (y-my)**2 < 260){ S.sel = -1; dossierCase(v); return; }
  }
  if (S.L.camaras) for (const s of S.cams){
    const [x,y] = markerPos(s);
    if ((x-mx)**2 + (y-my)**2 < 200){ S.sel = -1; dossierCam(s); return; }
  }
  const d = S.d; let best = -1, bd = 169;
  for (let i=0;i<S.N;i++){
    if (!pass(i)) continue;
    const x = px(d.lon[i]/1e4) - mx, y = py(d.lat[i]/1e4) - my;
    const q = x*x + y*y;
    if (q < bd){ bd = q; best = i; }
  }
  if (best >= 0){ S.sel = best; dossier(best); } else { S.sel = -1; $("#dossier").hidden = true; }
}

/* ───────────── ficha ───────────── */
const EVN = [[1,"declara registro en video"],[2,"declara fotografías"],[4,"menciona radar o control aéreo"],[8,"varios testigos"]];
const MESES = ["—","ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"];
const FLAGNAMES = [[1,"emergió del agua"],[2,"entró al agua"],[4,"relato sobre agua"],
                   [8,"desde embarcación"],[16,"orilla / costa"],[32,"coordenada sobre agua"],[64,"franja costera"]];
function durTxt(code){
  const s = Math.expm1(code/1000);
  if (s < 1) return "—";
  if (s < 60) return Math.round(s) + " s";
  if (s < 3600) return Math.round(s/60) + " min";
  return (s/3600).toFixed(1) + " h";
}
function dossier(i){
  const d = S.d, m = d.mar[i], cat = CAT[m];
  const place = d.places[d.place[i]] || "—";
  const h = d.hour[i], hh = h > 23 ? "—" : String(h).padStart(2,"0") + ":00";
  const tags = FLAGNAMES.filter(([b]) => d.flags[i] & b).map(([,n]) => `<em>${n}</em>`).join("");
  $("#dsTag").textContent = cat.n;
  $("#dsTag").style.color = cat.c;
  $("#dsBody").innerHTML = `
    <div class="ds-title">
      <h3>${place}</h3>
      <p>${d.day[i]||""} ${MESES[d.month[i]]||"—"} ${d.year[i]} · ${hh} LOCAL</p>
    </div>
    <div class="ds-grid">
      <div class="ds-cell"><span>FORMA</span><b>${(d.shapes[d.shape[i]]||"—").toUpperCase()}</b></div>
      <div class="ds-cell"><span>DURACIÓN</span><b>${durTxt(d.dur[i])}</b></div>
      <div class="ds-cell"><span>COSTA</span><b>${d.dcoast[i] >= 65535 ? "—" : fmt(d.dcoast[i])+" km"}</b></div>
      <div class="ds-cell"><span>COORDENADA</span><b style="font-size:9.5px">${(d.lat[i]/1e4).toFixed(3)}, ${(d.lon[i]/1e4).toFixed(3)}</b></div>
    </div>
    ${tags ? `<div class="ds-flags">${tags}</div>` : ""}
    <div class="ds-foot" style="color:var(--txt-dim)">
      <b style="color:var(--txt-faint);font-size:7.5px;letter-spacing:.2em">SOLIDEZ DEL REPORTE</b>
      <div class="solbar">${[1,2,3,4,5].map(k => `<i class="${d.sol[i] >= k ? "on" : ""}"></i>`).join("")}<span>${d.sol[i]} de 5</span></div>
      ${EVN.filter(([b]) => d.ev[i] & b).map(([,n]) => "· " + n).join("<br>")}
    </div>
    ${d.exp[i] ? `<div class="ds-foot" style="color:var(--txt-dim);border-left:2px solid var(--am)">
      <b style="color:var(--am);font-size:7.5px;letter-spacing:.2em">POSIBLE EXPLICACIÓN CONVENCIONAL</b><br>
      ${EXPL.filter(e => d.exp[i] & e.bit).map(e => e.d).join("<br>")}</div>` : ""}
    <div class="ds-foot">
      Reporte de la base NUFORC, geocodificado a nivel de ciudad: la coordenada marca la
      localidad desde la que se informó, no el punto exacto del objeto.
      <br><a href="https://nuforc.org/subndx/?id=${d.year[i]}" target="_blank" rel="noopener">Consultar archivo NUFORC ↗</a>
    </div>`;
  const rightPanel = !$("#panel").hidden && $("#panel").style.right !== "auto";
  $("#dossier").style.right = rightPanel ? "356px" : "48px";
  $("#dossier").hidden = false;
}
function dsOpen(){
  const rightPanel = !$("#panel").hidden && $("#panel").style.right !== "auto";
  $("#dossier").style.right = rightPanel ? "356px" : "48px";
  $("#dossier").hidden = false;
}
function dossierCase(v){
  const col = v.agua ? "var(--am)" : "var(--cy)";
  $("#dsTag").textContent = "EXPEDIENTE AUDIOVISUAL";
  $("#dsTag").style.color = col;
  $("#dsBody").innerHTML = `
    <div class="ds-title">
      <h3>${v.titulo}</h3>
      <p>${v.fecha.toUpperCase()}</p>
    </div>
    <div class="ds-cell" style="border-right:0"><span>LUGAR</span><b style="font-size:10px">${v.lugar}${v.aprox?" · posición aproximada":""}</b></div>
    <div class="ds-cell" style="border-right:0"><span>ORGANISMO</span><b style="font-size:10px">${v.organismo}</b></div>
    <div class="ds-cell" style="border-right:0"><span>SENSOR</span><b style="font-size:10px">${v.sensor}</b></div>
    <div class="ds-foot" style="color:var(--txt-dim)"><b style="color:${col};letter-spacing:.2em;font-size:7.5px">QUÉ MUESTRA</b><br>${v.muestra}</div>
    <div class="ds-foot" style="color:var(--txt-dim)"><b style="color:${col};letter-spacing:.2em;font-size:7.5px">ESTADO OFICIAL</b><br>${v.estado}</div>
    <div class="ds-foot">${v.enlaces.map(([t,u]) => `<a href="${u}" target="_blank" rel="noopener">${t} ↗</a>`).join("<br>")}</div>`;
  dsOpen();
}
function dossierCam(s){
  $("#dsTag").textContent = "CÁMARA DE CIELO";
  $("#dsTag").style.color = "#5ef2a8";
  $("#dsBody").innerHTML = `
    <div class="ds-title"><h3>${s.n}</h3><p>${s.o.toUpperCase()} · ${s.p.toUpperCase()}</p></div>
    <div class="ds-grid">
      <div class="ds-cell"><span>LATITUD</span><b>${s.lat.toFixed(3)}</b></div>
      <div class="ds-cell"><span>LONGITUD</span><b>${s.lon.toFixed(3)}</b></div>
    </div>
    <div class="ds-foot" style="color:var(--txt-dim)">${s.d}</div>
    <div class="ds-foot"><a href="${s.u}" target="_blank" rel="noopener">Abrir en el sitio del operador ↗</a></div>`;
  dsOpen();
}
$("#dsClose").onclick = () => { $("#dossier").hidden = true; S.sel = -1; };

/* ───────────── HUD ───────────── */
function hud(){
  $("#sbZoom").textContent = "Z " + S.view.z.toFixed(1);
  const kmPerPx = 40075 * Math.cos(S.view.cy*Math.PI/180) / sc();
  const bar = kmPerPx * 110;
  $("#sbScale").textContent = bar > 1000 ? Math.round(bar/100)*100 + " km" : bar > 10 ? Math.round(bar) + " km" : bar.toFixed(1) + " km";
  $("#mLayers").textContent = Object.values(S.L).filter(Boolean).length;
}
function clock(){
  const n = new Date();
  const p = x => String(x).padStart(2,"0");
  $("#mClock").textContent = `${p(n.getUTCHours())}:${p(n.getUTCMinutes())}:${p(n.getUTCSeconds())}Z`;
}

function countWindow(){
  let n = 0;
  for (let i=0;i<S.N;i++) if (pass(i)) n++;
  $("#tlCount").textContent = fmt(n);
  return n;
}
let countTimer = 0;
const countSoon = () => { clearTimeout(countTimer); countTimer = setTimeout(countWindow, 160); };

/* ───────────── raíles y paneles ───────────── */
const ICON = {
  capas:'<path d="M8 2 2 5.5 8 9l6-3.5L8 2Z"/><path d="M2 8.5 8 12l6-3.5M2 11.5 8 15l6-3.5"/>',
  mar:'<path d="M1 11c1.6-1.4 3.2-1.4 4.8 0s3.2 1.4 4.8 0 3.2-1.4 4.4 0"/><path d="M1 14c1.6-1.4 3.2-1.4 4.8 0s3.2 1.4 4.8 0 3.2-1.4 4.4 0"/><ellipse cx="8" cy="5" rx="5" ry="2"/><path d="M8 7v2"/>',
  analisis:'<path d="M2 14V7M6 14V3M10 14V9M14 14V5"/>',
  filtro:'<path d="M2 3h12l-4.6 5.4V14L6.6 12V8.4L2 3Z"/>',
  mapa:'<circle cx="8" cy="8" r="6.2"/><path d="M1.8 8h12.4M8 1.8c3 3.4 3 9 0 12.4M8 1.8c-3 3.4-3 9 0 12.4"/>',
  pantalla:'<rect x="1.6" y="3" width="12.8" height="9" rx="1"/><path d="M6 14h4"/>',
  escudo:'<path d="M8 1.6 13.4 3.8v4.4c0 3-2.2 5.2-5.4 6.2-3.2-1-5.4-3.2-5.4-6.2V3.8L8 1.6Z"/><path d="m5.6 8 1.8 1.8 3.2-3.6"/>',
  feed:'<circle cx="3.4" cy="12.6" r="1.3" fill="currentColor" stroke="none"/><path d="M3 8.6a4.4 4.4 0 0 1 4.4 4.4M3 4.4A8.6 8.6 0 0 1 11.6 13"/><path d="M12.4 3.2 14.8 5.6"/>',
  envios:'<path d="M2 4.5h12v8H2v-8Z"/><path d="m2 5 6 4.2L14 5"/><circle cx="12.6" cy="3.6" r="2.2" fill="currentColor" stroke="none"/>',
  video:'<rect x="1.4" y="4" width="9.6" height="8" rx="1"/><path d="M11 7.6 14.6 5.4v5.2L11 8.4Z"/><path d="M4.6 8h.01"/>',
  buscar:'<circle cx="7" cy="7" r="4.6"/><path d="M10.4 10.4 14.5 14.5"/>',
  stats:'<path d="M2 2v12h12"/><path d="M4.5 11 7 7l2.6 2.4L13 4"/>',
  uso:'<path d="M3 2h7l3 3v9H3V2Z"/><path d="M10 2v3h3"/><path d="M5.5 9.5c.9-.8 1.8-.8 2.6 0s1.7.8 2.4 0"/>',
  info:'<circle cx="8" cy="8" r="6.2"/><path d="M8 7.2v4M8 5.1v.1"/>',
  teclado:'<rect x="1.4" y="4" width="13.2" height="8" rx="1"/><path d="M4 7h.01M6.5 7h.01M9 7h.01M11.5 7h.01M5 9.6h6"/>',
};
const btn = (ic, tip, id) =>
  `<button data-p="${id}" data-tip="${tip}"><svg viewBox="0 0 16 16">${ICON[ic]}</svg><span class="badge" data-badge="${id}" hidden></span></button>`;

$("#railLeft").innerHTML =
  btn("capas","AVISTAMIENTOS","cap") + btn("mar","INTERFAZ MAR–AIRE","mar") +
  btn("feed","ÚLTIMOS VIDEOS","ult") + btn("video","REGISTRO VISUAL","vis") +
  btn("envios","ENVÍOS CIUDADANOS","env") + btn("escudo","EXPLICACIONES Y SOLIDEZ","exp") +
  btn("analisis","ANÁLISIS","ana") + btn("filtro","FILTROS","fil") +
  btn("mapa","CARTOGRAFÍA","geo") + btn("pantalla","PANTALLA","pan");
$("#railRight").innerHTML =
  btn("buscar","BUSCAR LUGAR","bus") + btn("stats","ESTADÍSTICAS","est") +
  btn("uso","INFORME USO","inf") + btn("info","MÉTODO Y FUENTE","met") + btn("teclado","ATAJOS","key");

document.querySelectorAll(".rail button").forEach(b => b.onclick = () => openPanel(b.dataset.p));
$("#panelClose").onclick = () => closePanel();
function refreshPanel(){ if (!S.panel) return; const P = PANELS[S.panel]; $("#panelBody").innerHTML = P.html(); P.bind?.(); }
function closePanel(){ $("#panel").hidden = true; S.panel = null; document.querySelectorAll(".rail button").forEach(b=>b.classList.remove("on")); }

function openPanel(id){
  if (S.panel === id) return closePanel();
  S.panel = id;
  document.querySelectorAll(".rail button").forEach(b => b.classList.toggle("on", b.dataset.p === id));
  const P = PANELS[id]; if (!P) return;
  $("#panelTitle").textContent = P.t;
  $("#panelBody").innerHTML = P.html();
  $("#panel").hidden = false;
  $("#panel").classList.toggle("wide", !!P.wide);
  $("#panel").style.left = id==="bus"||id==="est"||id==="inf"||id==="met"||id==="key" ? "auto" : "48px";
  $("#panel").style.right = id==="bus"||id==="est"||id==="inf"||id==="met"||id==="key" ? "48px" : "auto";
  P.bind?.();
  if (!$("#dossier").hidden)
    $("#dossier").style.right = $("#panel").style.right !== "auto" ? "356px" : "48px";
}

const rowHTML = (k, name, count, color, on) =>
  `<div class="row ${on?"on":""}" data-l="${k}">
     <div class="sw"><i></i></div>
     ${color?`<div class="chip" style="background:${color};box-shadow:0 0 7px ${color}"></div>`:""}
     <div class="nm">${name}</div><div class="ct">${count!=null?fmt(count):""}</div>
   </div>`;

function bindRows(){
  $("#panelBody").querySelectorAll("[data-l]").forEach(r => r.onclick = () => {
    const k = r.dataset.l; S.L[k] = S.L[k] ? 0 : 1;
    r.classList.toggle("on", !!S.L[k]);
    if (k === "scan") $("#fxScan").hidden = !S.L.scan;
    if (k === "leyenda") $("#legend").style.display = S.L.leyenda ? "" : "none";
    if (k === "ticker") $("#ticker").style.display = S.L.ticker ? "" : "none";
    mark(); hud(); countSoon(); saveURL();
  });
}

const PANELS = {
  cap:{ t:"AVISTAMIENTOS", html(){
    const c = S.counts;
    return `<div class="grp"><span>CATEGORÍA</span><span>REGISTROS</span></div>` +
      CAT.map((k,i)=> rowHTML(k.k, k.n, c[i], k.c, S.L[k.k])).join("") +
      `<div class="hint">Cada punto es un reporte ciudadano geocodificado a la localidad desde donde se informó. El color indica su relación con el agua.</div>`;
  }, bind: bindRows },

  mar:{ t:"INTERFAZ MAR–AIRE", html(){
    const f = S.st.rawFlags || {};
    const solo = !S.L.aereo;
    return `<div class="row ${solo?"on":""}" data-iso style="border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:9px 11px">
        <div class="sw"><i></i></div><div class="nm" style="color:${solo?"var(--cy)":"var(--txt-dim)"}">AISLAR CAPA MARÍTIMA</div>
        <div class="ct">${fmt(S.st.marine_total)}</div></div>
      <div class="hint">Apaga los ${fmt(S.counts[0])} reportes sin relación con el agua y deja solo la interfaz mar–aire.</div>
      <div class="grp"><span>CAPAS DE AGUA</span><span>REGISTROS</span></div>` +
      [1,2,3,4,5].map(i => rowHTML(CAT[i].k, CAT[i].n, S.counts[i], CAT[i].c, S.L[CAT[i].k])).join("") +
      `<div class="grp"><span>CONTEXTO</span></div>${rowHTML("bati","BATIMETRÍA",null,"#0f3a55",S.L.bati)}${rowHTML("rutas","RUTAS NAVIERAS",null,"#ffb340",S.L.rutas)}${rowHTML("naval","ZONAS DE ENTRENAMIENTO NAVAL",null,"#ff5a52",S.L.naval)}
       <div class="grp"><span>FILTRO ESTRICTO</span></div>
       <div class="row ${S.F.soloAgua?"on":""}" data-f="soloAgua"><div class="sw"><i></i></div>
         <div class="nm">SOLO COORDENADA SOBRE AGUA</div><div class="ct">${fmt(f["coordenada sobre agua"]||0)}</div></div>
       <div class="hint">Descarta todo reporte cuya coordenada caiga en tierra firme: quedan los informados desde el mar, lagos o islas menores no cartografiadas.</div>
       <div class="grp"><span>INDICIOS EN EL RELATO</span><span>CASOS</span></div>
       ${Object.entries(f).map(([k,v]) => `<div class="kv" style="padding:4px 11px">${k}<b>${fmt(v)}</b></div>`).join("")}
       <div class="hint">Detectado por análisis de texto sobre el resumen del reporte. Los relatos completos quedan en el archivo original de NUFORC.</div>`;
  }, bind(){
    bindRows();
    const iso = $("#panelBody").querySelector("[data-iso]");
    if (iso) iso.onclick = () => {
      const on = !S.L.aereo;
      if (on){ S.L.aereo = 1; } else { S.L.aereo = 0; for (let i=1;i<CAT.length;i++) S.L[CAT[i].k] = 1; }
      refreshPanel(); mark(); hud(); countSoon(); saveURL();
    };
    const r = $("#panelBody").querySelector('[data-f="soloAgua"]');
    if (r) r.onclick = () => { S.F.soloAgua = S.F.soloAgua ? 0 : 1; r.classList.toggle("on", !!S.F.soloAgua); mark(); countSoon(); saveURL(); };
  }},

  vis:{ t:"REGISTRO VISUAL", html(){
    const ev = S.st.evidence || {};
    const casos = S.vids.map(v => `
      <button data-v="${v.id}" style="border-left-color:${v.agua?"var(--am)":"var(--cy)"}">
        <b style="color:${v.agua?"var(--am)":"var(--cy)"}">${v.titulo}</b>
        <i>${v.fecha} · ${v.lugar}</i>
      </button>`).join("");
    const cams = S.cams.map((s,i) => `
      <button data-c="${i}" style="border-left-color:#5ef2a8">
        <b style="color:#5ef2a8">${s.n}</b><i>${s.o} · ${s.p}</i>
      </button>`).join("");
    return `<div class="grp"><span>CAPAS</span></div>` +
      rowHTML("casos","EXPEDIENTES OFICIALES", S.vids.length, "#ffb340", S.L.casos) +
      rowHTML("camaras","CÁMARAS DE CIELO", S.cams.length, "#5ef2a8", S.L.camaras) +
      `<div class="grp"><span>EVIDENCIA EN EL RELATO</span><span>REPORTES</span></div>` +
      EV.map(e => rowHTML(e.k, e.n, ev[e.k==="evVideo"?"video":e.k==="evFoto"?"foto":e.k==="evRadar"?"radar":"multitestigo"], e.c, S.L[e.k])).join("") +
      `<div class="hint">Marca con un anillo los reportes cuyo relato declara una grabación, fotografías, confirmación por radar o varios testigos. No incluye el material en sí: los archivos quedan en el origen.</div>
       <div class="grp"><span>EXPEDIENTES OFICIALES</span><span>${S.vids.filter(v=>v.latam).length} DE LATINOAMÉRICA</span></div>
       <div class="res">${casos}</div>
       <div class="hint">${S.vidNota}</div>
       <div class="grp"><span>CÁMARAS DE CIELO COMPLETO</span></div>
       <div class="res">${cams}</div>
       <div class="hint">${S.camNota}</div>`;
  }, bind(){
    bindRows();
    $("#panelBody").querySelectorAll("[data-v]").forEach(b => b.onclick = () => {
      const v = S.vids.find(x => x.id === b.dataset.v);
      S.L.casos = 1; flyTo(v.lon, v.lat, 5.4); dossierCase(v);
    });
    $("#panelBody").querySelectorAll("[data-c]").forEach(b => b.onclick = () => {
      const s = S.cams[+b.dataset.c];
      S.L.camaras = 1; flyTo(s.lon, s.lat, 6); dossierCam(s); mark();
    });
  }},

  ana:{ t:"ANÁLISIS", html(){
    return `<div class="grp"><span>REPRESENTACIÓN</span></div>` +
      rowHTML("calor","MAPA DE CALOR",null,"#ffb340",S.L.calor) +
      rowHTML("densidad","CUADRÍCULA DE DENSIDAD",null,"#34dfe8",S.L.densidad) +
      rowHTML("pulso","PULSO DE CASOS RAROS",null,"#ff5a52",S.L.pulso) +
      `<div class="hint">El mapa de calor normaliza sobre lo visible: al acercarte revela estructura local, no volumen absoluto.</div>
       <div class="grp"><span>LECTURA RÁPIDA</span></div>
       <div class="stat" style="border:0">
         <h3>REPORTES POR AÑO</h3>${sparkYears()}
         <h3 style="margin-top:14px">HORA DEL AVISTAMIENTO</h3>${sparkHours()}
       </div>`;
  }, bind: bindRows },

  fil:{ t:"FILTROS", html(){
    const sh = S.d.shapes.map((s,i) => `<button data-sh="${i}" class="${S.F.shapes.has(i)?"on":""}">${s}</button>`).join("");
    return `<div class="grp"><span>FORMA DECLARADA</span><button id="shClear" style="color:var(--cy);font-size:8px">LIMPIAR</button></div>
      <div class="chips" id="shapeChips">${sh}</div>
      <div class="grp"><span>FRANJA HORARIA</span></div>
      <div class="chips" id="hourChips">
        ${["TODAS","NOCHE 22–05","AMANECER 05–09","DÍA 09–17","ATARDECER 17–22"]
          .map((n,i)=>`<button data-h="${i-1}" class="${S.F.hour===i-1?"on":""}">${n}</button>`).join("")}
      </div>
      <div class="fld"><label>DURACIÓN MÍNIMA <b id="durLbl">sin límite</b></label>
        <input type="range" id="durR" min="0" max="9000" step="100" value="${S.F.dur}"></div>
      <div class="fld"><label>DISTANCIA MÁX. A LA COSTA <b id="coastLbl">${S.F.coast<0?"sin límite":fmt(S.F.coast)+" km"}</b></label>
        <input type="range" id="coastR" min="0" max="400" step="5" value="${S.F.coast<0?400:S.F.coast}"></div>
      <div class="hint">La distancia a la costa se calcula contra la línea de costa mundial; 0 km equivale a un reporte sobre el agua o en la orilla.</div>`;
  }, bind(){
    $("#shapeChips").querySelectorAll("[data-sh]").forEach(b => b.onclick = () => {
      const i = +b.dataset.sh;
      S.F.shapes.has(i) ? S.F.shapes.delete(i) : S.F.shapes.add(i);
      b.classList.toggle("on"); mark(); countSoon();
    });
    $("#shClear").onclick = () => { S.F.shapes.clear(); $("#shapeChips").querySelectorAll("button").forEach(b=>b.classList.remove("on")); mark(); countSoon(); };
    $("#hourChips").querySelectorAll("[data-h]").forEach(b => b.onclick = () => {
      S.F.hour = +b.dataset.h;
      $("#hourChips").querySelectorAll("button").forEach(x => x.classList.toggle("on", x === b));
      mark(); countSoon();
    });
    $("#durR").oninput = e => {
      S.F.dur = +e.target.value;
      $("#durLbl").textContent = S.F.dur ? "≥ " + durTxt(S.F.dur) : "sin límite";
      mark(); countSoon();
    };
    $("#coastR").oninput = e => {
      const v = +e.target.value; S.F.coast = v >= 400 ? -1 : v;
      $("#coastLbl").textContent = S.F.coast < 0 ? "sin límite" : fmt(v) + " km";
      mark(); countSoon();
    };
  }},

  geo:{ t:"CARTOGRAFÍA", html(){
    return `<div class="grp"><span>BASE</span></div>` +
      rowHTML("tierra","MASA CONTINENTAL",null,null,S.L.tierra) +
      rowHTML("lagos","LAGOS Y MARES INTERIORES",null,null,S.L.lagos) +
      rowHTML("fronteras","FRONTERAS",null,null,S.L.fronteras) +
      rowHTML("oceano","GRADIENTE OCEÁNICO",null,null,S.L.oceano) +
      `<div class="grp"><span>CONTEXTO MARÍTIMO</span></div>` +
      rowHTML("bati","BATIMETRÍA",null,"#0f3a55",S.L.bati) +
      rowHTML("rutas","RUTAS NAVIERAS",null,"#ffb340",S.L.rutas) +
      rowHTML("naval","ZONAS DE ENTRENAMIENTO NAVAL",null,"#ff5a52",S.L.naval) +
      `<div class="hint">Batimetría a 200, 1.000, 3.000 y 5.000 m (Natural Earth). Rutas navieras principales. Las zonas navales son áreas de ejercicio conocidas públicamente, dibujadas de forma aproximada: varios de los expedientes oficiales ocurrieron dentro de ellas.</div>
       <div class="grp"><span>REFERENCIAS</span></div>` +
      rowHTML("reticula","RETÍCULA Y ECUADOR",null,null,S.L.reticula) +
      rowHTML("terminador","TERMINADOR DÍA/NOCHE",null,"#ffb340",S.L.terminador) +
      `<div class="hint">El terminador se calcula en vivo desde la posición solar actual (UTC). Geometría: Natural Earth 1:50M.</div>`;
  }, bind: bindRows },

  pan:{ t:"PANTALLA", html(){
    return `<div class="grp"><span>INTERFAZ</span></div>` +
      rowHTML("scan","LÍNEAS DE BARRIDO",null,null,S.L.scan) +
      rowHTML("leyenda","LEYENDA",null,null,S.L.leyenda) +
      rowHTML("ticker","TELETIPO DE CASOS",null,null,S.L.ticker) +
      `<div class="hint">Pulsa F para pantalla completa y R para restablecer la vista.</div>`;
  }, bind: bindRows },

  bus:{ t:"BUSCAR LUGAR", html(){
    return `<div class="fld"><input type="search" id="q" placeholder="CIUDAD, ESTADO O PAÍS…" autocomplete="off"></div>
            <div class="res" id="res"><div class="hint">Escribe al menos tres letras. Busca entre ${fmt(S.d.places.length)} localidades con reportes.</div></div>`;
  }, bind(){
    const q = $("#q"); q.focus();
    q.oninput = () => {
      const t = q.value.trim().toLowerCase();
      if (t.length < 3){ $("#res").innerHTML = `<div class="hint">Escribe al menos tres letras.</div>`; return; }
      const hits = [];
      for (let p = 0; p < S.d.places.length && hits.length < 60; p++)
        if (S.d.places[p].toLowerCase().includes(t)) hits.push(p);
      if (!hits.length){ $("#res").innerHTML = `<div class="hint">Sin coincidencias.</div>`; return; }
      $("#res").innerHTML = hits.map(p => {
        let n = 0, first = -1;
        for (let i=0;i<S.N;i++) if (S.d.place[i] === p){ n++; if (first<0) first = i; }
        return `<button data-i="${first}"><b>${S.d.places[p]}</b><i>${fmt(n)} reporte${n>1?"s":""}</i></button>`;
      }).join("");
      $("#res").querySelectorAll("[data-i]").forEach(b => b.onclick = () => {
        const i = +b.dataset.i;
        flyTo(S.d.lon[i]/1e4, S.d.lat[i]/1e4, 8);
        S.sel = i; dossier(i);
      });
    };
  }},

  est:{ t:"ESTADÍSTICAS", html(){
    const st = S.st;
    const top = (st.topMarineCities||[]).slice(0,12)
      .map(([c,n]) => `<div class="kv">${c}<b>${fmt(n)}</b></div>`).join("");
    const shapes = Object.entries(st.byShapeMarine||{}).slice(0,10)
      .map(([s,n]) => `<div class="kv">${s}<b>${fmt(n)}</b></div>`).join("");
    return `<div class="stat" style="border:0">
        <div class="kv big">REGISTROS TOTALES<b>${fmt(st.total)}</b></div>
        <div class="kv big">CON COMPONENTE MARÍTIMA<b>${fmt(st.marine_total)}</b></div>
        <div class="kv big">COORDENADA SOBRE AGUA<b>${fmt(st.over_water)}</b></div>
        <div class="kv big">ENTRADA / SALIDA DEL AGUA<b>${fmt(st.uso_total)}</b></div>
        <div class="kv big">CON EXPLICACIÓN PROBABLE<b>${fmt((st.explained||{}).cualquiera)}</b></div>
        <div class="kv">archivo histórico hasta ${st.corte}<b>${fmt(st.total - st.ext)}</b></div>
        <div class="kv">extensión hasta ${st.hasta}<b>${fmt(st.ext)}</b></div>
        <div class="kv">reportes desde Latinoamérica<b>${fmt(st.latam)}</b></div>
      </div>
      <div class="stat"><h3>REPORTES POR AÑO</h3>${sparkYears()}</div>
      <div class="stat"><h3>HORA DEL AVISTAMIENTO · MARÍTIMOS</h3>${sparkHours(true)}</div>
      <div class="stat"><h3>LOCALIDADES COSTERAS MÁS ACTIVAS</h3>${top}</div>
      <div class="stat"><h3>FORMA EN REPORTES MARÍTIMOS</h3>${shapes}</div>
      <div class="stat"><h3>DURACIÓN MEDIANA</h3>
        <div class="kv">todos los reportes<b>${Math.round(st.medianDurAll)} s</b></div>
        <div class="kv">reportes marítimos<b>${Math.round(st.medianDurMarine)} s</b></div></div>`;
  }},

  inf:{ t:"INFORME USO", html(){
    const d = S.d, rows = [];
    for (let i=0;i<S.N;i++) if (d.mar[i] >= 4) rows.push(i);
    rows.sort((a,b) => d.mar[b]-d.mar[a] || d.year[b]-d.year[a]);
    return `<div class="hint">Objetos sumergidos no identificados: reportes cuyo relato describe al objeto entrando o saliendo del agua. ${rows.length} casos en todo el archivo.</div>
      <div class="res">${rows.map(i => `
        <button data-i="${i}" style="border-left-color:${CAT[d.mar[i]].c}">
          <b style="color:${CAT[d.mar[i]].c}">${CAT[d.mar[i]].n}</b>
          <i>${d.places[d.place[i]]} · ${MESES[d.month[i]]||""} ${d.year[i]} · ${d.shapes[d.shape[i]]}</i>
        </button>`).join("")}</div>`;
  }, bind(){
    $("#panelBody").querySelectorAll("[data-i]").forEach(b => b.onclick = () => {
      const i = +b.dataset.i;
      for (const c of CAT) S.L[c.k] = 1;
      S.F.y0 = Y0; S.F.y1 = Y1; syncTL();
      flyTo(S.d.lon[i]/1e4, S.d.lat[i]/1e4, 7);
      S.sel = i; dossier(i);
    });
  }},

  met:{ t:"MÉTODO Y FUENTE", html(){
    const f = S.st.rawFlags || {};
    return `<div class="hint" style="line-height:1.75">
      <b style="color:var(--cy)">ORIGEN</b><br>
      ${fmt(S.st.total)} reportes del National UFO Reporting Center (NUFORC), recopilados entre 1906 y ${S.st.hasta.slice(0,4)}.
      El tramo histórico (hasta ${S.st.corte}) viene del proyecto abierto <i>ufo-reports</i>; la extensión posterior,
      de la extracción publicada por <i>TidyTuesday</i> a partir del trabajo de Timothy Renner. Ambos geocodifican a la localidad del informante. Geometría costera: Natural Earth 1:50M.<br><br>

      <b style="color:var(--cy)">CÓMO SE MARCA LO MARÍTIMO</b><br>
      Dos vías independientes. La primera es geométrica: se calcula la distancia de cada coordenada a la
      línea de costa mundial y se prueba si cae sobre el mar o sobre un lago — ${fmt(f["coordenada sobre agua"]||0)}
      reportes caen sobre agua y ${fmt(f["franja costera ≤20 km"]||0)} dentro de los 20 km de costa.
      La segunda es textual: se buscan patrones en el resumen del reporte que describan el objeto entrando
      al agua, saliendo de ella, sobrevolándola o siendo visto desde una embarcación.<br><br>

      <b style="color:var(--cy)">LÍMITES QUE CONVIENE TENER PRESENTES</b><br>
      · La coordenada es la del pueblo o ciudad desde donde se informó, no la del objeto: un avistamiento
      "sobre el mar" puede aparecer tierra adentro.<br>
      · El archivo está fuertemente sesgado hacia Estados Unidos (${fmt(S.st.byCountry?.US||0)} de ${fmt(S.st.total)} reportes).<br>
      · Son testimonios sin verificar. Este visor cartografía <i>reportes</i>, no fenómenos confirmados.<br>
      · El resumen de texto está truncado en el origen, así que la detección textual subestima el total real.<br><br>

      <b style="color:var(--cy)">EXPLICACIONES Y SOLIDEZ</b><br>
      Las coincidencias con lluvias de meteoros, fechas de fuegos artificiales y lanzamientos orbitales se calculan por fecha y
      distancia; señalan una causa posible, no la demuestran. Los lanzamientos cubren hasta 2018. El índice de solidez mide
      cuánta información aporta el reporte, no la realidad del fenómeno.<br><br>
      <b style="color:var(--cy)">ARCHIVO ORIGINAL</b><br>
      <a href="https://nuforc.org" target="_blank" rel="noopener">nuforc.org ↗</a></div>`;
  }},

  key:{ t:"ATAJOS", html(){
    return `<div class="stat" style="border:0">
      ${[["R","restablecer vista"],["F","pantalla completa"],["H","ocultar interfaz"],
         ["ESPACIO","reproducir oleadas"],["+ / −","acercar y alejar"],["1 … 6","alternar categorías"],
         ["ESC","cerrar paneles"],["CLIC","abrir ficha del reporte"],["ARRASTRAR","desplazar el mapa"]]
        .map(([k,v]) => `<div class="kv"><b style="color:var(--cy)">${k}</b>${v}</div>`).join("")}</div>`;
  }},
};

/* ───────────── gráficos pequeños ───────────── */
function sparkYears(){
  const by = S.st.byYear, bm = S.st.byYearMarine || {};
  const ys = Object.keys(by).map(Number).filter(y => y >= 1945).sort((a,b)=>a-b);
  const max = Math.max(...ys.map(y => by[y]));
  return `<div class="bars">${ys.map(y => {
      const h = Math.max(1, by[y]/max*100), hm = (bm[y]||0)/max*100;
      return `<div style="height:${h}%" title="${y}: ${fmt(by[y])}"><div class="hot" style="position:absolute;bottom:0;left:0;right:0;height:${h?hm/h*100:0}%"></div></div>`;
    }).join("")}</div>
    <div class="axis"><span>${ys[0]}</span><span style="color:var(--am)">■ marítimos</span><span>${ys[ys.length-1]}</span></div>`;
}
function sparkHours(marine){
  const h = (marine ? S.st.byHourMarine : S.st.byHour) || {};
  const arr = Array.from({length:24}, (_,i) => h[i] || 0), max = Math.max(...arr,1);
  return `<div class="bars">${arr.map((v,i) =>
      `<div class="${i>=20||i<5?"hot":""}" style="height:${Math.max(1,v/max*100)}%" title="${i}:00 · ${fmt(v)}"></div>`).join("")}</div>
    <div class="axis"><span>00</span><span>06</span><span>12</span><span>18</span><span>23</span></div>`;
}

/* ───────────── línea de tiempo ───────────── */
const tlc = $("#tlCanvas"), tctx = tlc.getContext("2d");
const Y0 = 1906; let Y1 = 2023;
function drawTL(){
  const r = tlc.getBoundingClientRect();
  tlc.width = r.width*DPR; tlc.height = r.height*DPR;
  tctx.setTransform(DPR,0,0,DPR,0,0);
  tctx.clearRect(0,0,r.width,r.height);
  const by = S.st.byYear, bm = S.st.byYearMarine || {};
  const max = Math.max(...Object.values(by));
  const n = Y1-Y0+1, w = r.width/n;
  for (let y=Y0;y<=Y1;y++){
    const v = by[y]||0, vm = bm[y]||0, x = (y-Y0)*w;
    const h = Math.pow(v/max,.55)*r.height, hm = Math.pow(vm/max,.55)*r.height;
    tctx.fillStyle = "rgba(52,223,232,.42)"; tctx.fillRect(x, r.height-h, Math.max(1,w-.5), h);
    tctx.fillStyle = "rgba(255,179,64,.75)"; tctx.fillRect(x, r.height-hm, Math.max(1,w-.5), hm);
  }
  tctx.fillStyle = "rgba(207,230,238,.4)"; tctx.font = "7px ui-monospace,monospace";
  for (let y=1950;y<=Y1;y+=10){ const x=(y-Y0)*w; tctx.fillRect(x,0,.5,4); tctx.fillText(y, x+2, 9); }
}
function syncTL(){
  const t = $("#tlTrack").getBoundingClientRect(), n = Y1-Y0;
  const a = (S.F.y0-Y0)/n*t.width, b = (S.F.y1-Y0)/n*t.width;
  $("#tlSel").style.left = a+"px"; $("#tlSel").style.width = (b-a)+"px";
  $("#knobA").style.left = (a-4)+"px"; $("#knobB").style.left = (b-4)+"px";
  $("#tlLabel").textContent = `${S.F.y0} — ${S.F.y1}`;
  countSoon();
}
let knob = null;
["knobA","knobB"].forEach(id => $("#"+id).addEventListener("mousedown", e => { knob = id; e.preventDefault(); }));
$("#tlTrack").addEventListener("mousedown", e => {
  if (knob) return;
  const t = $("#tlTrack").getBoundingClientRect();
  const y = Math.round(Y0 + (e.clientX-t.left)/t.width*(Y1-Y0));
  knob = Math.abs(y-S.F.y0) < Math.abs(y-S.F.y1) ? "knobA" : "knobB";
  moveKnob(e);
});
window.addEventListener("mousemove", e => knob && moveKnob(e));
window.addEventListener("mouseup", () => { if (knob){ knob = null; saveURL(); } });
function moveKnob(e){
  const t = $("#tlTrack").getBoundingClientRect();
  const y = clamp(Math.round(Y0 + (e.clientX-t.left)/t.width*(Y1-Y0)), Y0, Y1);
  if (knob === "knobA") S.F.y0 = Math.min(y, S.F.y1-1); else S.F.y1 = Math.max(y, S.F.y0+1);
  syncTL(); mark();
}
$("#btnPlay").onclick = () => {
  S.play = !S.play;
  $("#btnPlay").textContent = S.play ? "❚❚" : "▶";
  if (S.play){
    if (S.F.y1 >= Y1) { S.F.y0 = Y0; S.F.y1 = Y0 + 4; }
    (function tick(){
      if (!S.play) return;
      S.F.y1 = Math.min(Y1, S.F.y1 + 1);
      if (S.F.y1 >= Y1){ S.play = 0; $("#btnPlay").textContent = "▶"; }
      syncTL(); mark();
      setTimeout(tick, 170);
    })();
  }
};

/* ───────────── leyenda y teletipo ───────────── */
function buildLegend(){
  $("#legend").innerHTML = `<h4>CLAVE DE CATEGORÍA</h4>` +
    CAT.map((c,i) => `<div><i style="background:${c.c};box-shadow:0 0 7px ${c.c}"></i>${c.n}<b>${fmt(S.counts[i])}</b></div>`).join("");
}
function buildTicker(){
  const d = S.d, rows = [];
  for (let i=0;i<S.N;i++) if (d.mar[i] >= RARE) rows.push(i);
  rows.sort((a,b) => d.mar[b]-d.mar[a] || d.year[b]-d.year[a]);
  const ultimos = (S.ult || []).slice(0, 12).map(u =>
    `<span><b style="color:${claseDe(u).c}">ÚLTIMO</b>${esc(u.titulo||"")}<em>${esc(u.fuente||"")}</em></span>`).join("");
  const casos = S.vids.map(v =>
    `<span><b style="color:${v.agua?"var(--am)":"var(--cy)"}">VIDEO OFICIAL</b>${v.titulo} · ${v.fecha}<em>${v.organismo.split(" ·")[0]}</em></span>`).join("");
  const items = ultimos + casos + rows.slice(0,70).map(i =>
    `<span><b>${CAT[d.mar[i]].n}</b>${d.places[d.place[i]]} · ${d.year[i]}<em>${d.shapes[d.shape[i]]}</em></span>`).join("");
  $("#tickerRun").innerHTML = items + items;
}

/* ───────────── URL ───────────── */
function saveURL(){
  const on = Object.keys(S.L).filter(k => S.L[k]);
  const p = new URLSearchParams({capas: on.join(","), y: `${S.F.y0}-${S.F.y1}`});
  history.replaceState(null, "", "?" + p.toString());
}
function readURL(){
  const p = new URLSearchParams(location.search);
  if (p.get("capas")){
    const on = new Set(p.get("capas").split(","));
    for (const k of Object.keys(S.L)) S.L[k] = on.has(k) ? 1 : 0;
  }
  const y = p.get("y");
  if (y && /^\d{4}-\d{4}$/.test(y)){
    S.F.y0 = clamp(+y.split("-")[0], Y0, Y1); S.F.y1 = clamp(+y.split("-")[1], Y0, Y1);
  }
}

/* ───────────── atajos ───────────── */
const toast = t => { const el = $("#toast"); el.textContent = t; el.classList.add("on"); clearTimeout(el._t); el._t = setTimeout(()=>el.classList.remove("on"), 1700); };
window.addEventListener("keydown", e => {
  if (e.target.matches("input")) { if (e.key === "Escape") e.target.blur(); return; }
  const k = e.key.toLowerCase();
  if (k === "r"){ S.view = {...S.home}; mark(); hud(); toast("VISTA RESTABLECIDA"); }
  else if (k === "f"){ document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen?.(); }
  else if (k === "h"){ document.body.classList.toggle("bare");
    document.querySelectorAll(".hud-top,.rail,.timeline,.statusbar,.legend,.panel,.dossier,.mapctl")
      .forEach(el => el.style.visibility = el.style.visibility === "hidden" ? "" : "hidden"); }
  else if (k === " "){ e.preventDefault(); $("#btnPlay").click(); }
  else if (k === "+" || k === "="){ zoomBy(.6); }
  else if (k === "-"){ zoomBy(-.6); }
  else if (k === "escape"){ closePanel(); $("#dossier").hidden = true; S.sel = -1; }
  else if (k >= "1" && k <= "6"){ const c = CAT[+k-1]; S.L[c.k] = S.L[c.k]?0:1; toast(c.n + (S.L[c.k]?" · ON":" · OFF"));
    mark(); hud(); countSoon(); refreshPanel(); }
});
$("#btnZoomIn").onclick = () => zoomBy(.7);
$("#btnZoomOut").onclick = () => zoomBy(-.7);
$("#btnReset").onclick = () => { S.view = {...S.home}; mark(); hud(); };

/* ───────────── arranque ───────────── */
function start(){
  Y1 = S.d.y1 || 2023; S.F.y1 = Y1;
  const tr = $("#tagRango"); if (tr) tr.textContent = Y0 + " — " + Y1;
  readURL();
  S.view.z = clamp(Math.log2(Math.max(innerWidth,900)*0.92/256), 1.2, 3.2);
  S.home = {...S.view};
  // índices por categoría
  S.catIdx = CAT.map(() => []); S.counts = CAT.map(() => 0);
  for (let i=0;i<S.N;i++){ const m = S.d.mar[i]; S.catIdx[m].push(i); S.counts[m]++; }
  S.catIdx = S.catIdx.map(a => Int32Array.from(a));

  $("#mCount").textContent = fmt(S.st.total);
  $("#mMarine").textContent = fmt(S.st.marine_total);
  $("#mUso").textContent = fmt(S.st.uso_total);
  $("#fxScan").hidden = !S.L.scan;

  resize(); buildLegend(); buildTicker(); drawTL(); syncTL(); hud();
  clock(); setInterval(clock, 1000);
  setInterval(() => { if (S.L.terminador) mark(); }, 60000);
  window.addEventListener("resize", () => { resize(); drawTL(); syncTL(); });
  boot.classList.add("off");
  setTimeout(() => boot.remove(), 600);
  openPanel("mar");
  raf = requestAnimationFrame(loop);
  initCaps();
}
/* ═══════════════════════════════════════════════════════════════
   ENVÍOS CIUDADANOS · enlaces a videos alojados en su plataforma
   El video nunca se descarga ni se re-aloja: se incrusta desde el
   origen, con crédito y enlace al autor.
   ═══════════════════════════════════════════════════════════════ */

const PLAT = [
  {k:"youtube",  n:"YouTube",   re:/(?:youtube\.com\/(?:watch\?v=|shorts\/|embed\/|live\/)|youtu\.be\/)([A-Za-z0-9_-]{6,24})/,
   emb:id => "https://www.youtube.com/embed/" + id},
  {k:"vimeo",    n:"Vimeo",     re:/vimeo\.com\/(?:video\/)?(\d{6,12})/,
   emb:id => "https://player.vimeo.com/video/" + id},
  {k:"tiktok",   n:"TikTok",    re:/tiktok\.com\/[^\s]*\/video\/(\d{8,25})/,
   emb:id => "https://www.tiktok.com/embed/v2/" + id},
  {k:"instagram",n:"Instagram", re:/instagram\.com\/(?:p|reel|tv)\/([A-Za-z0-9_-]{5,30})/,
   emb:id => "https://www.instagram.com/p/" + id + "/embed"},
  {k:"x",        n:"X",         re:/(?:twitter|x)\.com\/[^\/\s]+\/status\/(\d{8,25})/, emb:null},
];
function parseVideo(u){
  if (!/^https:\/\//i.test(u || "")) return null;
  for (const p of PLAT){
    const m = u.match(p.re);
    if (m) return {plataforma:p.k, nombre:p.n, videoId:m[1], emb: p.emb ? p.emb(m[1]) : ""};
  }
  return null;
}
function videoCard(url, nombre){
  const u = okUrl(url); if (!u) return "";
  const pv = !window.claude && parseVideo(u);
  if (pv && pv.emb) return `<div class="embed"><iframe src="${esc(pv.emb)}" loading="lazy" allowfullscreen
      referrerpolicy="strict-origin-when-cross-origin"></iframe></div>`;
  const n = (nombre || "la plataforma").toUpperCase();
  return `<a class="vcard" href="${esc(u)}" target="_blank" rel="noopener">
      <span class="vplay"></span>
      <span class="vtxt">VER EN ${esc(n)} &#8599;</span>
      <span class="vsub">se abre en su sitio de origen · nada se aloja aquí</span>
    </a>`;
}
const esc = s => String(s ?? "").replace(/[&<>"']/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const okUrl = u => /^https:\/\/[\w.-]+\//.test(u || "") ? u : "";

S.env = []; S.rev = {}; S.db = null; S.user = null;
S.caps = {state:"cargando", write:null, owner:false, uid:null, ro:false};
S.form = {url:"", fecha:"", hora:"", lugar:"", lat:"", lon:"", tipo:0, forma:"", desc:"", autoria:"propio", credito:"", contacto:"", lic:false};
S.pickMode = 0;

const estadoDe = e => (S.rev[e.id] || {}).estado || "pendiente";

async function initCaps(){
  let db = null, user = null;
  try { db = await window.claude?.use?.("db"); } catch(e){}
  try { user = await window.claude?.use?.("user"); } catch(e){}
  S.db = db || null; S.user = user || null;
  if (user){
    try { S.caps.owner = !!(await user.isOwner()); } catch(e){}
    try { S.caps.write = await user.can("data.write"); } catch(e){}
    try { S.caps.uid = await user.id(); } catch(e){}
  }
  if (!db){
    S.caps.state = "sin-enlace"; S.ultState = "sin-enlace";
    try {  // modo autónomo: instantánea del feed empaquetada con el sitio
      const snap = await (await fetch("data/recientes.json")).json();
      S.ult = (snap.items || []).sort((a,b) => String(b.fechaPub).localeCompare(String(a.fechaPub)));
      S.zonas = snap.zonas || []; S.ultState = "ok";
      $("#mUlt").textContent = fmt(S.ult.filter(u => diasDe(u) <= 30).length);
      mark(); buildTicker();
    } catch(e){}
    ultStatus(); ultList(); if (S.panel === "env") refreshPanel(); return;
  }
  const t = setTimeout(() => {
    if (S.caps.state === "cargando"){ S.caps.state = "lento"; envStatus(); }
  }, 10000);
  db.collection("envios").onSnapshot(snap => {
    clearTimeout(t);
    S.env = snap.docs.map(d => Object.assign({id:d.id}, d.data()))
                     .filter(e => typeof e.lat === "number" && typeof e.lon === "number");
    S.caps.state = "ok"; mark(); envList(); envStatus();
  }, e => { clearTimeout(t); S.caps.state = "error"; S.caps.err = e.code; envStatus(); });
  subUltimos(db); subZonas(db);
  db.collection("revision").onSnapshot(snap => {
    S.rev = {}; snap.docs.forEach(d => S.rev[d.id] = d.data() || {});
    mark(); envList();
  }, () => {});
}

/* ─── dibujo ─── */
function drawEnvios(c){
  if (!S.L.envios || !S.env.length) return;
  for (const e of S.env){
    const est = estadoDe(e);
    if (est === "descartado" && !S.caps.owner) continue;
    const x = px(e.lon), y = py(e.lat);
    if (x < -30 || x > W+30 || y < -30 || y > H+30) continue;
    const ver = est === "verificado";
    const col = est === "descartado" ? "#6b4a4a" : ver ? (CAT[e.tipo] || CAT[0]).c : "#8fa6b3";
    c.strokeStyle = col; c.lineWidth = 1.1; c.globalAlpha = ver ? 1 : .72;
    c.beginPath(); c.moveTo(x, y-6.5); c.lineTo(x+6.5, y); c.lineTo(x, y+6.5); c.lineTo(x-6.5, y);
    c.closePath(); c.stroke();
    c.fillStyle = col; c.globalAlpha = ver ? .45 : .16; c.fill();
    if (ver){ c.globalAlpha = .9; c.fillRect(x-1, y-1, 2, 2); }
    c.globalAlpha = 1;
  }
}

/* ─── ficha ─── */
function dossierEnv(e){
  const est = estadoDe(e), cat = CAT[e.tipo] || CAT[0];
  const col = est === "verificado" ? cat.c : est === "descartado" ? "#6b4a4a" : "#8fa6b3";
  const url = okUrl(e.url), emb = okUrl(e.emb);
  const marco = videoCard(url, e.nombre);
  $("#dsTag").textContent = "REPORTE CIUDADANO · " + est.toUpperCase();
  $("#dsTag").style.color = col;
  $("#dsBody").innerHTML = `
    ${marco}
    <div class="ds-title">
      <h3>${esc(e.lugar || "Sin lugar declarado")}</h3>
      <p>${esc(e.fecha || "sin fecha")}${e.hora ? " · " + esc(e.hora) : ""} · ${esc((e.nombre||"").toUpperCase())}</p>
    </div>
    <div class="ds-grid">
      <div class="ds-cell"><span>CATEGORÍA</span><b style="font-size:9.5px;color:${col}">${esc(cat.n)}</b></div>
      <div class="ds-cell"><span>FORMA</span><b style="font-size:9.5px">${esc(e.forma || "—")}</b></div>
      <div class="ds-cell"><span>COORDENADA</span><b style="font-size:9px">${(+e.lat).toFixed(3)}, ${(+e.lon).toFixed(3)}</b></div>
      <div class="ds-cell"><span>ORIGEN</span><b style="font-size:9px">${e.autoria === "propio" ? "autor del video" : "terceros"}</b></div>
    </div>
    ${e.desc ? `<div class="ds-foot" style="color:var(--txt-dim)">${esc(e.desc)}</div>` : ""}
    <div class="ds-foot">
      ${e.credito ? "Crédito declarado: <b style='color:var(--txt)'>" + esc(e.credito) + "</b><br>" : ""}
      ${url ? `<a href="${esc(url)}" target="_blank" rel="noopener">Ver en ${esc(e.nombre)} ↗</a>` : ""}
    </div>
    ${S.caps.owner ? `<div class="ds-flags" style="gap:6px">
        <button class="mini" data-rev="verificado" data-id="${esc(e.id)}">VERIFICAR</button>
        <button class="mini warn" data-rev="descartado" data-id="${esc(e.id)}">DESCARTAR</button>
        <button class="mini" data-rev="pendiente" data-id="${esc(e.id)}">PENDIENTE</button>
      </div>` : ""}
    <div class="ds-foot" style="font-size:7.5px">El video permanece alojado en ${esc(e.nombre || "su plataforma")}: NEREO solo lo enlaza. Antes de usarlo en una pieza propia hace falta licencia del autor.</div>`;
  $("#dossier").querySelectorAll("[data-rev]").forEach(b => b.onclick = () => marcarRevision(b.dataset.id, b.dataset.rev, e));
  dsOpen();
}

async function marcarRevision(id, estado, e){
  if (!S.db) return;
  try {
    const ref = S.db.doc("revision/" + id);
    const snap = await ref.get();
    const body = {estado, at: new Date().toISOString()};
    snap.exists ? await ref.update(body) : await ref.set(body);
    toast("ESTADO: " + estado.toUpperCase());
    if (e) setTimeout(() => dossierEnv(e), 350);
  } catch(err){
    toast(err && err.code === "invalid_argument" ? "SIN PERMISO PARA CURAR" : "NO SE PUDO GUARDAR");
  }
}

/* ─── panel ─── */
function envStatus(){
  const el = $("#envStatus"); if (!el) return;
  const s = S.caps.state;
  const txt = s === "ok" ? `ENLACE ACTIVO · ${fmt(S.env.length)} REPORTE${S.env.length===1?"":"S"}`
    : s === "cargando" ? "ABRIENDO ENLACE CON LA BANDEJA…"
    : s === "lento" ? "LA BANDEJA NO RESPONDE AÚN"
    : s === "error" ? "ERROR DE ENLACE (" + esc(S.caps.err || "") + ")"
    : "SIN ENLACE · ABRE LA PÁGINA PUBLICADA CON SESIÓN INICIADA";
  el.textContent = txt;
  el.className = "envstat " + (s === "ok" ? "ok" : s === "cargando" ? "" : "bad");
}

function envList(){
  const el = $("#envList"); if (!el) return;
  if (!S.env.length){
    el.innerHTML = `<div class="hint">Todavía no hay reportes. El primero que envíes aparece aquí y en el mapa al instante.</div>`;
    return;
  }
  const orden = [...S.env].sort((a,b) => String(b.creado||"").localeCompare(String(a.creado||"")));
  el.innerHTML = orden.map(e => {
    const est = estadoDe(e), cat = CAT[e.tipo] || CAT[0];
    const col = est === "verificado" ? cat.c : est === "descartado" ? "#6b4a4a" : "#8fa6b3";
    return `<button data-env="${esc(e.id)}" style="border-left-color:${col}">
        <b style="color:${col}">${esc(e.lugar || "sin lugar")} · ${esc(e.fecha || "")}</b>
        <i>${esc((e.nombre||"").toUpperCase())} · ${esc(cat.n.toLowerCase())} · ${esc(est)}</i>
      </button>`;
  }).join("");
  el.querySelectorAll("[data-env]").forEach(b => b.onclick = () => {
    const e = S.env.find(x => x.id === b.dataset.env);
    if (!e) return;
    S.L.envios = 1; flyTo(e.lon, e.lat, 7); dossierEnv(e);
  });
}

const TPL = {
  es: `Hola [nombre]:

Vi tu video del [fecha] en [lugar] y me gustaría incluirlo en NEREO, un mapa público y sin fines comerciales de avistamientos aéreos y marítimos no identificados.

Lo que propongo es enlazarlo con el reproductor de [plataforma]: el video sigue alojado en tu cuenta, conservas las vistas y el crédito queda a tu nombre tal como me indiques. No lo descargo ni lo resubo a ningún canal.

Si además te interesa que aparezca en una pieza editorial que estoy produciendo, eso necesitaría una licencia simple por escrito, que puedo enviarte para que la revises. No pido exclusividad ni la propiedad del material: sigue siendo tuyo y puedes retirar el permiso cuando quieras.

¿Te parece? Con un sí por aquí me basta para el enlace.

Gracias,
Simón Rojas · NOVA AUDIOVISUAL`,
  en: `Hi [name],

I came across your video from [date] in [place] and I'd like to include it in NEREO, a public, non-commercial map of unidentified aerial and maritime sightings.

What I'm proposing is linking it through the [platform] player: the video stays hosted on your account, you keep the views, and the credit reads exactly as you tell me. I won't download it or re-upload it to any channel.

If you'd also be open to it appearing in an editorial piece I'm producing, that would need a simple written licence, which I can send over for you to review. I'm not asking for exclusivity or ownership: the footage stays yours and you can withdraw permission at any time.

Would that work? A yes here is enough for the link.

Thanks,
Simón Rojas · NOVA AUDIOVISUAL`,
  lic: `Confirmación de permiso (para que el autor responda con este texto)

Yo, [nombre completo], autor del video publicado en [enlace], autorizo a NOVA AUDIOVISUAL SPA a enlazar e incrustar ese video en el visor NEREO, y a usar un extracto en piezas editoriales sobre el caso, con crédito a [nombre o cuenta]. Declaro ser el autor del material o contar con derecho para otorgar este permiso. Esta autorización no es exclusiva y puedo revocarla avisando por este mismo medio.

Fecha: [fecha]`
};

PANELS.env = { t:"ENVÍOS CIUDADANOS", wide:true, html(){
    const cats = CAT.map((c,i) => `<option value="${i}">${c.n}</option>`).join("");
    const formas = ["", ...S.d.shapes].map(s => `<option value="${s}">${s || "— forma —"}</option>`).join("");
    return `
    <div id="envStatus" class="envstat">ABRIENDO ENLACE…</div>

    <div class="grp"><span>NUEVO REPORTE</span></div>
    <div class="frm">
      <label>ENLACE DEL VIDEO
        <input type="text" id="fUrl" placeholder="https://… YouTube, Vimeo, TikTok, Instagram o X" value="${esc(S.form.url)}"></label>
      <div id="fUrlInfo" class="fnote"></div>
      <div class="frow">
        <label>FECHA<input type="date" id="fFecha" value="${esc(S.form.fecha)}"></label>
        <label>HORA<input type="time" id="fHora" value="${esc(S.form.hora)}"></label>
      </div>
      <label>LUGAR<input type="text" id="fLugar" placeholder="Ciudad, región, país" value="${esc(S.form.lugar)}"></label>
      <div class="frow">
        <label>LATITUD<input type="text" id="fLat" placeholder="-33.045" value="${esc(S.form.lat)}"></label>
        <label>LONGITUD<input type="text" id="fLon" placeholder="-71.619" value="${esc(S.form.lon)}"></label>
      </div>
      <button class="mini wide" id="fPick">MARCAR EN EL MAPA</button>
      <div class="frow">
        <label>CATEGORÍA<select id="fTipo">${cats}</select></label>
        <label>FORMA<select id="fForma">${formas}</select></label>
      </div>
      <label>QUÉ SE VE<textarea id="fDesc" rows="3" maxlength="400" placeholder="Describe brevemente el objeto y la circunstancia">${esc(S.form.desc)}</textarea></label>
      <label>ORIGEN DEL VIDEO<select id="fAut">
        <option value="propio">Lo grabé yo</option>
        <option value="tercero">Lo grabó otra persona</option></select></label>
      <label>CRÉDITO<input type="text" id="fCred" placeholder="Nombre o @cuenta a acreditar" value="${esc(S.form.credito)}"></label>
      <label class="chk"><input type="checkbox" id="fLic">
        <span>Declaro que soy el autor del video o que cuento con su permiso para enlazarlo aquí, y entiendo que NEREO solo lo incrusta desde su plataforma de origen.</span></label>
      <button class="send" id="fSend">ENVIAR REPORTE</button>
      <div id="fMsg" class="fnote"></div>
    </div>

    <div class="grp"><span>BANDEJA</span></div>
    <div class="res" id="envList"><div class="hint">—</div></div>

    <div class="grp"><span>SOLICITUD DE PERMISO</span></div>
    <div class="hint">Para pedir autorización al autor antes de usar su material en una pieza propia. Edita los campos entre corchetes.</div>
    <div class="tpl"><div class="tplhead">ESPAÑOL<button class="mini" data-cp="es">COPIAR</button></div><pre id="tplEs">${esc(TPL.es)}</pre></div>
    <div class="tpl"><div class="tplhead">INGLÉS<button class="mini" data-cp="en">COPIAR</button></div><pre id="tplEn">${esc(TPL.en)}</pre></div>
    <div class="tpl"><div class="tplhead">CONFIRMACIÓN DEL AUTOR<button class="mini" data-cp="lic">COPIAR</button></div><pre id="tplLic">${esc(TPL.lic)}</pre></div>
    <div class="hint">Esta confirmación sirve como constancia del permiso para enlazar y citar. Para una licencia comercial o de larga duración, que la revise un abogado.</div>`;
  },
  bind(){
    envStatus(); envList();
    const g = id => $("#"+id);
    const sync = () => {
      S.form.url = g("fUrl").value.trim(); S.form.fecha = g("fFecha").value;
      S.form.hora = g("fHora").value; S.form.lugar = g("fLugar").value;
      S.form.lat = g("fLat").value; S.form.lon = g("fLon").value;
      S.form.tipo = +g("fTipo").value; S.form.forma = g("fForma").value;
      S.form.desc = g("fDesc").value; S.form.autoria = g("fAut").value;
      S.form.credito = g("fCred").value; S.form.lic = g("fLic").checked;
    };
    g("fTipo").value = S.form.tipo; g("fForma").value = S.form.forma;
    g("fAut").value = S.form.autoria; g("fLic").checked = S.form.lic;
    ["fUrl","fFecha","fHora","fLugar","fLat","fLon","fTipo","fForma","fDesc","fAut","fCred","fLic"]
      .forEach(id => { const el = g(id); if (el) el.addEventListener("input", sync); });
    g("fUrl").addEventListener("input", () => {
      const v = parseVideo(g("fUrl").value.trim());
      const n = $("#fUrlInfo");
      if (!g("fUrl").value.trim()) { n.textContent = ""; n.className = "fnote"; return; }
      n.textContent = v ? "Reconocido: " + v.nombre + (v.emb ? " · se puede incrustar" : " · se mostrará como enlace")
                        : "Enlace no reconocido. Solo YouTube, Vimeo, TikTok, Instagram y X.";
      n.className = "fnote " + (v ? "ok" : "bad");
    });
    g("fPick").onclick = () => {
      S.pickMode = 1; toast("HAZ CLIC EN EL MAPA PARA FIJAR LA COORDENADA");
    };
    g("fSend").onclick = () => enviarReporte();
    $("#panelBody").querySelectorAll("[data-cp]").forEach(b => b.onclick = async () => {
      const t = TPL[b.dataset.cp];
      try { await navigator.clipboard.writeText(t); toast("TEXTO COPIADO"); }
      catch(e){
        const pre = b.closest(".tpl").querySelector("pre");
        const r = document.createRange(); r.selectNodeContents(pre);
        const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r);
        toast("SELECCIONADO · COPIA CON CTRL+C");
      }
    });
  }
};

async function enviarReporte(){
  const m = $("#fMsg"); const fail = t => { m.textContent = t; m.className = "fnote bad"; };
  const f = S.form;
  if (!S.db) return fail("Sin enlace con la bandeja. Abre la página publicada con la sesión iniciada.");
  const v = parseVideo(f.url);
  if (!v) return fail("Falta un enlace válido de YouTube, Vimeo, TikTok, Instagram o X.");
  if (!f.fecha) return fail("Falta la fecha del avistamiento.");
  const lat = parseFloat(f.lat), lon = parseFloat(f.lon);
  if (!isFinite(lat) || !isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180)
    return fail("Falta la coordenada. Usa «marcar en el mapa» o escríbela a mano.");
  if (!f.lic) return fail("Marca la casilla de autoría y permiso.");
  m.textContent = "Enviando…"; m.className = "fnote";
  const doc = {
    url: f.url, plataforma: v.plataforma, nombre: v.nombre, videoId: v.videoId, emb: v.emb,
    fecha: f.fecha, hora: f.hora || "", lugar: f.lugar.slice(0,120), lat, lon,
    tipo: f.tipo|0, forma: f.forma || "", desc: f.desc.slice(0,400),
    autoria: f.autoria, credito: f.credito.slice(0,80),
    licencia: true, uid: S.caps.uid || "", creado: new Date().toISOString()
  };
  try {
    await S.db.collection("envios").add(doc);
    m.textContent = "Reporte enviado. Queda como pendiente hasta que se verifique."; m.className = "fnote ok";
    S.form = {url:"",fecha:"",hora:"",lugar:"",lat:"",lon:"",tipo:0,forma:"",desc:"",autoria:"propio",credito:"",contacto:"",lic:false};
    setTimeout(() => { if (S.panel === "env") refreshPanel(); }, 900);
  } catch(err){
    if (err && err.code === "invalid_argument"){ S.caps.ro = true; fail("Esta sesión no tiene permiso de escritura sobre la bandeja."); }
    else fail("No se pudo guardar (" + esc(err && err.code || "error") + "). Intenta de nuevo.");
  }
}

/* ═══════════════════════════════════════════════════════════════
   ÚLTIMOS VIDEOS · feed vivo, alimentado por la tarea diaria que
   escribe en la colección "recientes" de la base del artefacto.
   ═══════════════════════════════════════════════════════════════ */

S.ult = []; S.ultState = "cargando";
const CLASE = {
  oficial:{n:"MATERIAL OFICIAL", c:"#ffb340"},
  prensa: {n:"PRENSA",           c:"#34dfe8"},
  redes:  {n:"REDES SOCIALES",   c:"#9d7bff"},
};
const claseDe = u => CLASE[u.clase] || CLASE.redes;
const diasDe = u => {
  const t = Date.parse(u.fechaPub || u.creado || "");
  return isFinite(t) ? (Date.now() - t) / 864e5 : 999;
};
function fechaCorta(s){
  const d = new Date(s);
  if (isNaN(d)) return s || "—";
  return d.toLocaleDateString("es-CL", {day:"2-digit", month:"short", year:"numeric"});
}

function subUltimos(db){
  const t = setTimeout(() => { if (S.ultState === "cargando"){ S.ultState = "lento"; ultStatus(); } }, 10000);
  db.collection("recientes").orderBy("fechaPub", "desc").limit(60).onSnapshot(snap => {
    clearTimeout(t);
    S.ult = snap.docs.map(d => Object.assign({id:d.id}, d.data()));
    S.ultState = "ok";
    $("#mUlt").textContent = fmt(S.ult.filter(u => diasDe(u) <= 30).length);
    mark(); ultList(); ultStatus(); buildTicker();
  }, e => { clearTimeout(t); S.ultState = "error"; ultStatus(); });
}

/* ─── mapa ─── */
function drawUltimos(c, t){
  if (!S.L.ultimos || !S.ult.length) return;
  const ph = (Math.sin(t/780)+1)/2;
  for (const u of S.ult){
    if (typeof u.lat !== "number" || typeof u.lon !== "number") continue;
    const x = px(u.lon), y = py(u.lat);
    if (x < -40 || x > W+40 || y < -40 || y > H+40) continue;
    const col = claseDe(u).c, nuevo = diasDe(u) <= 3;
    if (nuevo){
      c.strokeStyle = col; c.globalAlpha = .5*(1-ph); c.lineWidth = 1;
      c.beginPath(); c.arc(x, y, 7 + ph*9, 0, 6.284); c.stroke();
    }
    c.globalAlpha = 1; c.strokeStyle = col; c.lineWidth = 1.2;
    c.beginPath(); c.arc(x, y, 5, 0, 6.284); c.stroke();
    c.fillStyle = col; c.globalAlpha = .4; c.fill(); c.globalAlpha = 1;
    c.beginPath();
    c.moveTo(x, y-8.5); c.lineTo(x, y-11.5); c.moveTo(x, y+8.5); c.lineTo(x, y+11.5);
    c.moveTo(x-8.5, y); c.lineTo(x-11.5, y); c.moveTo(x+8.5, y); c.lineTo(x+11.5, y);
    c.stroke();
    if (S.view.z > 2.8){
      c.font = "8px ui-monospace,monospace"; c.fillStyle = col; c.globalAlpha = .85;
      c.fillText(String(u.titulo || "").toUpperCase().slice(0, 30), x+14, y+3);
      c.globalAlpha = 1;
    }
  }
}

/* ─── ficha ─── */
function dossierUlt(u){
  const cl = claseDe(u);
  const yt = parseVideo(u.url || "");
  const marco = videoCard(u.url, yt && yt.nombre);
  const links = (u.enlaces || []).filter(x => Array.isArray(x) && okUrl(x[1]))
    .map(([t2,u2]) => `<a href="${esc(u2)}" target="_blank" rel="noopener">${esc(t2)} ↗</a>`).join("<br>");
  $("#dsTag").textContent = cl.n;
  $("#dsTag").style.color = cl.c;
  $("#dsBody").innerHTML = `
    ${marco}
    <div class="ds-title">
      <h3>${esc(u.titulo || "")}</h3>
      <p>${esc(fechaCorta(u.fechaPub))}${u.fechaEvento ? " · EVENTO " + esc(u.fechaEvento) : ""}</p>
    </div>
    <div class="ds-grid">
      <div class="ds-cell"><span>LUGAR</span><b style="font-size:9.5px">${esc(u.lugar || "no declarado")}</b></div>
      <div class="ds-cell"><span>ESTADO</span><b style="font-size:9.5px;color:${cl.c}">${esc(u.estado || "sin verificar")}</b></div>
    </div>
    ${u.resumen ? `<div class="ds-foot" style="color:var(--txt-dim)">${esc(u.resumen)}</div>` : ""}
    <div class="ds-foot">
      ${u.fuente ? `<b style="color:var(--txt-faint);font-size:7.5px;letter-spacing:.2em">FUENTE</b><br>${esc(u.fuente)}<br>` : ""}
      ${okUrl(u.url) ? `<a href="${esc(u.url)}" target="_blank" rel="noopener">Abrir el registro ↗</a><br>` : ""}
      ${links}
    </div>
    <div class="ds-foot" style="font-size:7.5px">Material alojado en su medio de origen; NEREO solo enlaza. Un registro en este feed es un reporte publicado, no un hecho verificado.</div>`;
  dsOpen();
}

/* ─── panel ─── */
function ultStatus(){
  const el = $("#ultStatus"); if (!el) return;
  const s = S.ultState;
  if (s === "ok"){
    const reciente = S.ult[0];
    el.textContent = reciente
      ? `ÚLTIMA ENTRADA · ${fechaCorta(reciente.fechaPub).toUpperCase()} · ${fmt(S.ult.length)} EN CARTERA`
      : "SIN ENTRADAS TODAVÍA · LA TAREA DIARIA LAS IRÁ SUMANDO";
    el.className = "envstat ok";
  } else {
    el.textContent = s === "cargando" ? "ABRIENDO EL FEED…"
      : s === "lento" ? "EL FEED NO RESPONDE AÚN"
      : s === "error" ? "ERROR DE ENLACE CON EL FEED"
      : "SIN ENLACE · ABRE LA PÁGINA PUBLICADA CON SESIÓN INICIADA";
    el.className = "envstat " + (s === "cargando" ? "" : "bad");
  }
}

function ultList(){
  const pre = $("#escPre"); if (pre) pre.textContent = escaleta();
  const el = $("#ultList"); if (!el) return;
  if (!S.ult.length){
    el.innerHTML = `<div class="hint">Aún no hay entradas en el feed.</div>`;
    return;
  }
  el.innerHTML = S.ult.map(u => {
    const cl = claseDe(u), d = diasDe(u);
    const edad = d < 1 ? "hoy" : d < 2 ? "ayer" : d < 30 ? Math.round(d) + " días" : fechaCorta(u.fechaPub);
    const zz = zonaDe(u);
    return `<button data-ult="${esc(u.id)}" style="border-left-color:${cl.c}">
        <b style="color:${cl.c}">${esc(u.titulo || "")}</b>
        <i>${zz ? `<span style="color:var(--cy)">◉ ${esc(zz.n)}</span> · ` : ""}${esc(edad)} · ${esc(u.fuente || "")} · ${esc(u.lugar || "sin lugar")}</i>
      </button>`;
  }).join("");
  el.querySelectorAll("[data-ult]").forEach(b => b.onclick = () => {
    const u = S.ult.find(x => x.id === b.dataset.ult); if (!u) return;
    S.L.ultimos = 1;
    if (typeof u.lat === "number" && typeof u.lon === "number") flyTo(u.lon, u.lat, 5.5);
    dossierUlt(u); mark();
  });
}

PANELS.ult = { t:"ÚLTIMOS VIDEOS", html(){
    return `<div id="ultStatus" class="envstat">ABRIENDO EL FEED…</div>
      <div class="grp"><span>CAPA</span></div>
      ${rowHTML("ultimos","MOSTRAR EN EL MAPA", null, "#ffb340", S.L.ultimos)}
      <div class="hint">Registros audiovisuales publicados en los últimos días: material oficial, cobertura de prensa y videos difundidos en redes. Una tarea diaria revisa las fuentes y suma lo nuevo; nada se descarga, todo queda enlazado a su origen.</div>
      <div class="grp"><span>CARTERA</span><span>MÁS RECIENTE PRIMERO</span></div>
      <div class="res" id="ultList"><div class="hint">—</div></div>
      <div class="grp"><span>ZONAS DE VIGILANCIA</span></div>
      <div id="zonaList"></div>
      <div class="frm" style="padding-top:0"><div class="frow">
        <label>NOMBRE<input type="text" id="zN" placeholder="Costa central"></label>
        <label>RADIO KM<input type="text" id="zK" value="300"></label></div>
        <button class="mini wide" id="zPick">MARCAR EL CENTRO EN EL MAPA Y GUARDAR</button></div>
      <div class="grp"><span>ESCALETA SEMANAL</span><button class="mini" id="escCopy">COPIAR</button></div>
      <div class="tpl" style="margin-top:4px"><pre id="escPre" style="max-height:230px"></pre></div>
      <div class="hint">Se arma sola con lo publicado en los últimos siete días, ordenada por zona de vigilancia y tipo de fuente. Es el punto de partida para el guion del informe en video.</div>
      <div class="grp"><span>LEYENDA</span></div>
      ${Object.entries(CLASE).map(([k,v]) =>
        `<div class="row" style="cursor:default"><div class="chip" style="background:${v.c};box-shadow:0 0 7px ${v.c}"></div>
         <div class="nm">${v.n}</div></div>`).join("")}
      <div class="hint">El pulso marca lo publicado en las últimas 72 horas. Un registro aquí es un reporte difundido, no un hecho confirmado: la ficha indica siempre el estado y la fuente.</div>`;
  },
  bind(){
    bindRows(); ultStatus(); ultList(); zonaList();
    $("#zPick").onclick = () => {
      const n = $("#zN").value.trim(), km = parseFloat($("#zK").value);
      if (!n || !isFinite(km) || km <= 0) return toast("FALTA NOMBRE O RADIO");
      S.pickMode = {zona:{n: n.slice(0,40), km: Math.min(5000, Math.round(km))}};
      toast("HAZ CLIC EN EL MAPA PARA FIJAR EL CENTRO DE LA ZONA");
    };
    $("#escCopy").onclick = async () => {
      try { await navigator.clipboard.writeText(escaleta()); toast("ESCALETA COPIADA"); }
      catch(e){ toast("SELECCIONA EL TEXTO Y COPIA CON CTRL+C"); }
    };
  }
};

/* ═══════════════════════════════════════════════════════════════
   NEREO v2 · explicaciones, solidez, contexto marítimo,
   zonas de vigilancia y escaleta semanal
   ═══════════════════════════════════════════════════════════════ */

const EXPL = [
  {k:"xMet",  bit:1, c:"#9d7bff", s:"meteoros",     n:"LLUVIA DE METEOROS",
   d:"Ocurrió dentro de la ventana de máximo de una lluvia de meteoros mayor y la forma declarada es luminosa."},
  {k:"xFuego",bit:2, c:"#ff8a5c", s:"fuegos",       n:"FUEGOS Y FAROLILLOS",
   d:"Fecha de fuegos artificiales y farolillos: 4 de julio, Año Nuevo o equivalente local."},
  {k:"xLanz", bit:4, c:"#5ef2a8", s:"lanzamientos", n:"LANZAMIENTO ORBITAL",
   d:"Coincide en fecha con un lanzamiento orbital de EE.UU. y está a menos de 800 km de un puerto espacial."},
];

function drawExpl(c){
  const d = S.d;
  for (const e of EXPL){
    if (!S.L[e.k]) continue;
    c.strokeStyle = e.c; c.lineWidth = 1; c.globalAlpha = .8;
    c.beginPath();
    for (let i=0;i<S.N;i++){
      if (!(d.exp[i] & e.bit) || !pass(i)) continue;
      const x = px(d.lon[i]/1e4), y = py(d.lat[i]/1e4);
      if (x<-10||x>W+10||y<-10||y>H+10) continue;
      c.moveTo(x-3.5,y-3.5); c.lineTo(x+3.5,y+3.5); c.moveTo(x+3.5,y-3.5); c.lineTo(x-3.5,y+3.5);
    }
    c.stroke(); c.globalAlpha = 1;
  }
}

/* ─── contexto marítimo ─── */
const kmPx = lat => sc() / (40075 * Math.max(.2, Math.cos(lat*Math.PI/180)));
function drawBati(c){
  const M = S.marx; if (!M) return;
  c.fillStyle = "#0a1a29"; c.fillRect(0,0,W,H);
  drawRings(c, M.bat["200"],  "#08141f");
  drawRings(c, M.bat["1000"], "#060f19");
  drawRings(c, M.bat["3000"], "#050b13");
  drawRings(c, M.bat["5000"], "#03070d");
}
function drawRutas(c){
  const M = S.marx; if (!M) return;
  c.save(); c.setLineDash([2,4]);
  for (const mayor of [0,1]){
    c.beginPath();
    for (const [t, l] of M.lanes){
      if (t !== mayor) continue;
      let prev = null;
      for (let i=0;i<l.length;i++){
        const x = px(l[i][0]), y = py(l[i][1]);
        if (i && Math.abs(l[i][0] - prev) < 180) c.lineTo(x,y); else c.moveTo(x,y);
        prev = l[i][0];
      }
    }
    c.strokeStyle = mayor ? "rgba(255,179,64,.34)" : "rgba(255,179,64,.16)"; c.lineWidth = mayor ? .9 : .6; c.stroke();
  }
  c.restore();
}
function drawNaval(c){
  const M = S.marx; if (!M) return;
  c.save(); c.setLineDash([4,3]); c.font = "8px ui-monospace,monospace";
  for (const [n, la, lo, km] of M.naval){
    const x = px(lo), y = py(la), r = km * kmPx(la);
    if (x<-r-40||x>W+r+40||y<-r-40||y>H+r+40) continue;
    c.strokeStyle = "rgba(255,90,82,.5)"; c.fillStyle = "rgba(255,90,82,.05)"; c.lineWidth = 1;
    c.beginPath(); c.arc(x,y,Math.max(4,r),0,6.284); c.fill(); c.stroke();
    if (S.view.z > 3){ c.fillStyle = "rgba(255,120,110,.85)"; c.fillText(n.toUpperCase(), x - r, y - r - 4); }
  }
  c.restore();
}
function drawPuertos(c){
  const M = S.marx; if (!M) return;
  c.font = "8px ui-monospace,monospace";
  for (const [n, la, lo] of M.puertos){
    const x = px(lo), y = py(la);
    if (x<-30||x>W+30||y<-30||y>H+30) continue;
    c.strokeStyle = "#5ef2a8"; c.fillStyle = "#5ef2a8"; c.lineWidth = 1.1;
    c.beginPath(); c.moveTo(x, y-7); c.lineTo(x+5, y+4); c.lineTo(x-5, y+4); c.closePath(); c.stroke();
    c.fillRect(x-1, y-1, 2, 2);
    if (S.view.z > 2.6){ c.globalAlpha = .8; c.fillText(n.toUpperCase(), x+9, y+3); c.globalAlpha = 1; }
  }
}

/* ─── zonas de vigilancia ─── */
S.zonas = []; S.zonaForm = {n:"", km:300, lat:null, lon:null};
function distKm(la1, lo1, la2, lo2){
  const r = Math.PI/180, a = Math.sin((la2-la1)*r/2)**2 + Math.cos(la1*r)*Math.cos(la2*r)*Math.sin((lo2-lo1)*r/2)**2;
  return 12742 * Math.asin(Math.sqrt(a));
}
const zonaDe = u => (typeof u.lat === "number" && typeof u.lon === "number")
  ? S.zonas.find(z => distKm(u.lat, u.lon, z.lat, z.lon) <= z.km) : null;
function subZonas(db){
  db.doc("config/zonas").onSnapshot(snap => {
    const d = snap.exists ? snap.data() : null;
    S.zonas = (d && Array.isArray(d.zonas) ? d.zonas : []).filter(z => typeof z.lat === "number" && typeof z.lon === "number");
    mark(); zonaList(); ultList();
  }, () => {});
}
function drawZonas(c){
  if (!S.L.ultimos || !S.zonas.length) return;
  c.save(); c.setLineDash([6,4]); c.font = "8px ui-monospace,monospace";
  for (const z of S.zonas){
    const x = px(z.lon), y = py(z.lat), r = z.km * kmPx(z.lat);
    if (x<-r-40||x>W+r+40||y<-r-40||y>H+r+40) continue;
    c.strokeStyle = "rgba(52,223,232,.55)"; c.lineWidth = 1;
    c.beginPath(); c.arc(x, y, Math.max(5, r), 0, 6.284); c.stroke();
    c.fillStyle = "rgba(52,223,232,.8)"; c.fillText("VIGILANCIA · " + String(z.n||"").toUpperCase().slice(0,26), x - Math.min(r, 70), y - r - 5);
  }
  c.restore();
}
async function guardarZonas(z){
  if (!S.db) return toast("SIN ENLACE CON LA BASE");
  try { await S.db.doc("config/zonas").set({zonas: z, at: new Date().toISOString()}); toast("ZONAS ACTUALIZADAS"); }
  catch(e){ toast(e && e.code === "invalid_argument" ? "SIN PERMISO PARA EDITAR ZONAS" : "NO SE PUDO GUARDAR"); }
}
function zonaList(){
  const el = $("#zonaList"); if (!el) return;
  el.innerHTML = S.zonas.length ? S.zonas.map((z,i) => {
      const n = S.ult.filter(u => typeof u.lat === "number" && distKm(u.lat,u.lon,z.lat,z.lon) <= z.km).length;
      return `<div class="kv" style="padding:5px 11px;align-items:center">
        <span><b style="color:var(--cy)">${esc(z.n)}</b> · ${fmt(z.km)} km · ${n} en cartera</span>
        <button class="mini warn" data-zdel="${i}">QUITAR</button></div>`;
    }).join("")
    : `<div class="hint">Sin zonas. Define una y la tarea diaria te avisará primero de lo que caiga dentro.</div>`;
  el.querySelectorAll("[data-zdel]").forEach(b => b.onclick = () => guardarZonas(S.zonas.filter((_,i) => i !== +b.dataset.zdel)));
}

/* ─── escaleta semanal ─── */
function escaleta(){
  let sem = S.ult.filter(u => diasDe(u) <= 7);
  const titulo = sem.length ? "ÚLTIMOS 7 DÍAS" : "ÚLTIMAS ENTRADAS";
  if (!sem.length) sem = S.ult.slice(0, 6);
  const orden = {oficial:0, prensa:1, redes:2};
  sem = [...sem].sort((a,b) => (zonaDe(b)?1:0) - (zonaDe(a)?1:0) || (orden[a.clase]??3) - (orden[b.clase]??3));
  const hoy = new Date().toLocaleDateString("es-CL", {day:"numeric", month:"long", year:"numeric"});
  const lineas = sem.map((u,i) => [
    `${i+1}. ${u.titulo}`,
    `   Qué: ${u.resumen || "—"}`,
    `   Dónde y cuándo: ${u.lugar || "no declarado"}${u.fechaEvento ? " · " + u.fechaEvento : ""}`,
    `   Estado: ${u.estado || "sin verificar"} · Tipo: ${claseDe(u).n.toLowerCase()}${zonaDe(u) ? " · EN ZONA DE VIGILANCIA" : ""}`,
    `   Fuente: ${u.fuente || "—"} · ${u.url || ""}`,
    `   Imagen: enlazar o licenciar antes de usar el registro original.`
  ].join("\n")).join("\n\n");
  return `NEREO · ESCALETA DEL INFORME SEMANAL\n${hoy} · ${titulo} · ${sem.length} casos\n\n` +
    `APERTURA\n   Panorama de la semana: ${sem.length} registros, ${sem.filter(u=>u.clase==="oficial").length} con material oficial, ` +
    `${sem.filter(u=>/explicad/i.test(u.estado||"")).length} con explicación propuesta.\n\n${lineas}\n\n` +
    `CIERRE\n   Recordatorio editorial: un registro difundido no es un hecho verificado. Citar siempre fuente y estado.`;
}

/* ─── panel EXPLICACIONES ─── */
PANELS.exp = { t:"EXPLICACIONES Y SOLIDEZ", html(){
    const x = S.st.explained || {}, bs = S.st.bySol || {};
    const max = Math.max(...Object.values(bs), 1);
    return `<div class="hint" style="padding-top:10px">Antes de afirmar, descartar. Estas capas marcan con una cruz los reportes que coinciden con una causa convencional conocida. Coincidir no es demostrar: es una razón para mirar el caso con más cuidado.</div>
      <div class="grp"><span>COINCIDENCIAS</span><span>REPORTES</span></div>
      ${EXPL.map(e => rowHTML(e.k, e.n, x[e.s], e.c, S.L[e.k])).join("")}
      ${rowHTML("puertos","PUERTOS ESPACIALES", (S.marx?.puertos||[]).length, "#5ef2a8", S.L.puertos)}
      <div class="row ${S.F.sinExp?"on":""}" data-f2="sinExp" style="border-top:1px solid var(--line);margin-top:6px"><div class="sw"><i></i></div>
        <div class="nm">OCULTAR LO EXPLICABLE</div><div class="ct">−${fmt(x.cualquiera||0)}</div></div>
      <div class="hint">Quita del mapa todo reporte con al menos una coincidencia. Lo que queda es el residuo que vale la pena estudiar.</div>
      <div class="grp"><span>ÍNDICE DE SOLIDEZ</span></div>
      <div class="fld"><label>SOLIDEZ MÍNIMA <b id="solLbl">${S.F.sol ? S.F.sol + " de 5" : "sin filtro"}</b></label>
        <input type="range" id="solR" min="0" max="4" step="1" value="${S.F.sol}"></div>
      <div class="stat" style="border:0;padding-top:0">
        <div class="bars" style="height:44px">${[0,1,2,3,4,5].map(k =>
          `<div style="height:${Math.max(2,(bs[k]||0)/max*100)}%" title="${k}: ${fmt(bs[k]||0)}"></div>`).join("")}</div>
        <div class="axis"><span>0</span><span>1</span><span>2</span><span>3</span><span>4</span><span>5</span></div>
      </div>
      <div class="hint">Cada reporte parte en 1 y suma un punto por registro visual declarado, por confirmación de radar, por varios testigos y por una duración entre uno y sesenta minutos. Pierde uno si coincide con una explicación. Mide cuánta información trae el reporte, no si el fenómeno es real.</div>
      <div class="grp"><span>EL EFECTO 4 DE JULIO</span></div>
      <div class="hint">En Estados Unidos el archivo acumula <b style="color:var(--am)">${fmt(S.st.july4||0)}</b> reportes fechados un 4 de julio, contra un promedio de <b style="color:var(--txt)">${fmt(Math.round(S.st.mediaDiaUS||0))}</b> para un día cualquiera del calendario. Es la huella de los fuegos artificiales en los datos.</div>`;
  },
  bind(){
    bindRows();
    const r = $("#panelBody").querySelector('[data-f2="sinExp"]');
    r.onclick = () => { S.F.sinExp = S.F.sinExp ? 0 : 1; r.classList.toggle("on", !!S.F.sinExp); mark(); countSoon(); };
    $("#solR").oninput = e => { S.F.sol = +e.target.value;
      $("#solLbl").textContent = S.F.sol ? S.F.sol + " de 5" : "sin filtro"; mark(); countSoon(); };
  }
};

load();
})();
