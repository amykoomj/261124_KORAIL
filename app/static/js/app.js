/* 매출 분석 — 화면 스크립트.
   원본 아티팩트의 렌더링/그래프 설정을 그대로 두고, 저장소만 localStorage → 서버 API(fetch)로 바꿨다.
   localStorage에는 개인 화면 설정(선택 해제한 지점, 선택 분기)만 남긴다. */
(() => {
'use strict';
const $=s=>document.querySelector(s);
const esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const won=n=>Math.round(n).toLocaleString('ko-KR')+'원';
const ppl=n=>Math.round(n).toLocaleString('ko-KR')+'명';
const short=n=>{const a=Math.abs(n);return a>=1e8?(n/1e8).toFixed(a>=1e9?0:1)+'억':a>=1e4?Math.round(n/1e4).toLocaleString('ko-KR')+'만':String(Math.round(n))};
const PAL={light:['#2a78d6','#eb6834','#1baf7a','#eda100','#e87ba4','#008300','#6250d6','#e34948'],
           dark:['#3987e5','#d95926','#199e70','#c98500','#d55181','#0ca30c','#9085e9','#e66767']};
const ACTION_LABEL={delete:'행 삭제',clear_sample:'예시 데이터 지우기',reset:'데이터 초기화',import:'CSV 일괄 입력'};

/* ---------- 개인 화면 설정 (localStorage) ---------- */
const VIEW_KEY='sales-analysis-view-v1';
let view={off:[],fq:'all',barQ:''};
try{const v=JSON.parse(localStorage.getItem(VIEW_KEY));if(v&&typeof v==='object')view={...view,...v,off:Array.isArray(v.off)?v.off:[]}}catch(e){}
const saveView=()=>{try{localStorage.setItem(VIEW_KEY,JSON.stringify(view))}catch(e){}};

/* ---------- 서버 데이터 캐시 ---------- */
let D={branches:[],quarters:[],rows:[],summary:null,chart:null,status:{sample_count:0,undo_count:0}};
let sort={k:'quarter',dir:1},editId=null;

const isDark=()=>{const t=document.documentElement.dataset.theme;return t?t==='dark':matchMedia('(prefers-color-scheme: dark)').matches};
const colorOf=ci=>PAL[isDark()?'dark':'light'][Math.min(Math.max(ci|0,0),7)];
const branchColor=name=>{const b=D.branches.find(x=>x.name===name);return colorOf(b?b.color_index:7)};

/* ---------- 검증 (서버 validators.py와 같은 규칙) ---------- */
const QRE=/^\d{4}-Q[1-4]$/;
const normQ=v=>{v=String(v).trim().toUpperCase().replace(/\s+/g,'');const m=v.match(/^(\d{4})[-.\/]?Q?([1-4])Q?$/);return m?`${m[1]}-Q${m[2]}`:v};
const toInt=v=>{const s=String(v).replace(/[,\s원명]/g,'');return /^\d+$/.test(s)?Number(s):NaN};
const check=(q,b,a,c)=>{const e=[];q=normQ(q);b=String(b).trim();const A=toInt(a),C=toInt(c);
  if(!QRE.test(q))e.push('분기는 2026-Q1 형식으로 입력하세요');
  if(!b)e.push('지점명을 입력하세요');else if(b.length>30)e.push('지점명은 30자 이내로 입력하세요');
  if(isNaN(A))e.push('매출 금액은 0 이상의 숫자만 입력하세요');
  if(isNaN(C))e.push('고객 수는 숫자만 입력하세요');else if(C<1)e.push('고객 수는 1 이상이어야 합니다');
  return {e,row:{quarter:q,branch:b,amount:A,customers:C}}};

/* ---------- API ---------- */
class ApiError extends Error{constructor(m,status,field){super(m);this.status=status;this.field=field}}
const net=on=>{const el=$('#netMsg');el.hidden=!on;if(on)el.textContent='서버에 연결할 수 없습니다. 서버(python run.py)가 실행 중인지 확인한 뒤 새로고침하세요.'};
async function api(method,url,body){
  const opt={method,headers:{Accept:'application/json'}};
  if(body instanceof FormData)opt.body=body;
  else if(body!==undefined){opt.headers['Content-Type']='application/json';opt.body=JSON.stringify(body)}
  let res;
  try{res=await fetch(url,opt)}catch(e){net(true);throw new ApiError('서버에 연결할 수 없습니다.',0)}
  net(false);
  let data=null;try{data=await res.json()}catch(e){}
  if(!res.ok||(data&&data.ok===false))throw new ApiError((data&&data.error)||`요청을 처리하지 못했습니다 (${res.status})`,res.status,data&&data.field);
  return data;
}
const msg=(el,t,ok)=>{el.textContent=t;el.className='msg '+(ok?'ok':'err')};

/* ---------- 필터 → 쿼리스트링 ---------- */
const selectedIds=()=>D.branches.filter(b=>!view.off.includes(b.name)).map(b=>b.id);
function qs(extra={}){const p=new URLSearchParams();
  if(view.fq!=='all')p.set('quarter',view.fq);
  if(D.branches.some(b=>view.off.includes(b.name)))p.set('branches',selectedIds().join(','));
  for(const [k,v] of Object.entries(extra))if(v)p.set(k,v);
  const s=p.toString();return s?'?'+s:''}

/* ---------- 불러오기 ---------- */
const setLoading=on=>document.querySelectorAll('.fig').forEach(f=>f.classList.toggle('loading',on));
let seq=0;
async function loadMeta(){
  const [branches,quarters,status]=await Promise.all([api('GET','/api/branches'),api('GET','/api/quarters'),api('GET','/api/status')]);
  D.branches=branches;D.quarters=quarters;D.status=status;
  view.off=view.off.filter(n=>branches.some(b=>b.name===n));
  if(view.fq!=='all'&&!quarters.includes(view.fq))view.fq='all';
  saveView();
}
async function loadData(){
  const my=++seq;setLoading(true);
  try{
    const [rows,summary,chart]=await Promise.all([api('GET','/api/sales'+qs()),api('GET','/api/summary'+qs()),api('GET','/api/chart-data'+qs({bar_quarter:view.barQ}))]);
    if(my!==seq)return false;  // 더 최근 요청이 있으면 버림
    D.rows=rows;D.summary=summary;D.chart=chart;return true;
  }finally{if(my===seq)setLoading(false)}
}
async function refresh(){
  try{await loadMeta();renderFilters();if(await loadData())renderData()}
  catch(e){if(e.status!==0)msg($('#tblMsg'),e.message)}
}

/* ---------- 렌더링 ---------- */
function fillSelect(sel,opts,val,allLabel){sel.innerHTML=(allLabel?`<option value="all">${allLabel}</option>`:'')+opts.map(o=>`<option>${esc(o)}</option>`).join('');sel.value=val}

function renderFilters(){const q=D.quarters;
  fillSelect($('#fQ'),q,view.fq,'전체 분기');
  fillSelect($('#barQ'),q,q.includes(view.barQ)?view.barQ:(q[q.length-1]||''));
  $('#fB').innerHTML=D.branches.map(b=>`<label class="chip"><input type="checkbox" value="${esc(b.name)}" ${view.off.includes(b.name)?'':'checked'}><i class="dot" style="background:${colorOf(b.color_index)}"></i>${esc(b.name)}</label>`).join('');
  $('#branchList').innerHTML=D.branches.map(b=>`<option value="${esc(b.name)}">`).join('')}

function renderCards(){const s=D.summary;if(!s)return;const fq=view.fq,has=s.count>0;
  let chg='—',cls='',chgSub='비교할 이전 분기 없음';
  if(s.qoq){const p=s.qoq.rate;chg=(p>0?'▲ ':p<0?'▼ ':'')+Math.abs(p).toFixed(1)+'%';cls=p>0?'up':p<0?'down':'';chgSub=`${s.qoq.from} → ${s.qoq.to}`}
  const top=s.top_branch;
  const cards=[['총매출',has?won(s.total_amount):'—',fq==='all'?'선택한 전체 기간':fq],['총고객수',has?ppl(s.total_customers):'—','누적 고객'],
    ['평균 객단가',s.avg_arpu!=null?won(s.avg_arpu):'—','총매출 ÷ 총고객수'],['매출 1위 지점',top?top.name:'—',top?won(top.amount):'데이터 없음'],['전 분기 대비',chg,chgSub]];
  $('#cards').innerHTML=cards.map(([t,v,sub],i)=>`<div class="card"><span>${t}</span><b class="${i===4?cls:''}" title="${esc(v)}">${esc(v)}</b><span>${esc(sub)}</span></div>`).join('');
  $('#headline').textContent=top?`${top.name} 지점이 매출을 이끌고 있습니다`:'매출 분석';
  $('#lede').textContent=has?`${fq==='all'?'전체 분기':fq} 기준, ${s.branch_count}개 지점의 매출 ${short(s.total_amount)}원, 고객 ${short(s.total_customers)}명입니다.`:'아래에서 데이터를 입력하면 요약과 그래프가 바로 그려집니다.'}

function renderTable(){const rs=[...D.rows];
  rs.sort((a,b)=>{const x=a[sort.k],y=b[sort.k];return (typeof x==='number'?x-y:String(x).localeCompare(String(y),'ko'))*sort.dir||a.branch.localeCompare(b.branch,'ko')});
  document.querySelectorAll('#tbl th[data-k]').forEach(th=>{const on=th.dataset.k===sort.k;th.setAttribute('aria-sort',on?(sort.dir>0?'ascending':'descending'):'none');th.textContent=th.textContent.replace(/ [▲▼]$/,'')+(on?(sort.dir>0?' ▲':' ▼'):'')});
  $('#tbl tbody').innerHTML=rs.length?rs.map(r=>r.id===editId?
    `<tr data-id="${r.id}"><td><input id="eQ" value="${esc(r.quarter)}"></td><td><input id="eB" value="${esc(r.branch)}" maxlength="30"></td><td><input id="eA" inputmode="numeric" value="${r.amount}"></td><td><input id="eC" inputmode="numeric" value="${r.customers}"></td><td></td><td class="num act"><button data-a="ok" class="pri">저장</button><button data-a="cancel">취소</button></td></tr>`:
    `<tr data-id="${r.id}"><td>${esc(r.quarter)}</td><td><i class="dot" style="display:inline-block;margin-right:6px;background:${branchColor(r.branch)}"></i>${esc(r.branch)}</td><td class="num">${won(r.amount)}</td><td class="num">${ppl(r.customers)}</td><td class="num">${won(r.arpu)}</td><td class="num act"><button data-a="edit">수정</button><button data-a="del">삭제</button></td></tr>`).join('')
    :`<tr><td colspan="6" class="empty">표시할 데이터가 없습니다. 위에서 데이터를 추가하거나 필터를 확인하세요.</td></tr>`;
  const A=rs.reduce((s,r)=>s+r.amount,0),C=rs.reduce((s,r)=>s+r.customers,0);
  $('#tbl tfoot').innerHTML=rs.length?`<tr><td colspan="2">합계 (${rs.length}건)</td><td class="num">${won(A)}</td><td class="num">${ppl(C)}</td><td class="num">${C?won(A/C):'—'}</td><td></td></tr>`:'';
  const hasSample=D.status.sample_count>0;
  $('#sampleNote').hidden=!hasSample;$('#clrSample').disabled=!hasSample;
  $('#undoBtn').hidden=!D.status.undo_count;
  $('#expCsv').disabled=$('#expXlsx').disabled=!rs.length}

const charts={};
function theme(){const cs=getComputedStyle(document.documentElement);return{ink:cs.getPropertyValue('--ink2').trim()||'#4a5a70',line:cs.getPropertyValue('--line').trim()||'#dde3ea',bg:cs.getPropertyValue('--panel').trim()||'#fff'}}
function draw(id,cfg){charts[id]?.destroy();charts[id]=new Chart(document.getElementById(id),cfg)}
function renderCharts(){const cd=D.chart;if(!cd)return;
  if(typeof Chart==='undefined'){document.querySelectorAll('.fig').forEach(f=>{f.classList.remove('loading');f.innerHTML='<p class="empty">그래프 라이브러리(static/vendor/chart.umd.js)를 불러오지 못했습니다.</p>'});return}
  const T=theme(),narrow=innerWidth<520,fq=view.fq,q=cd.quarters;
  Chart.defaults.font.family=getComputedStyle(document.body).fontFamily;Chart.defaults.color=T.ink;Chart.defaults.borderColor=T.line;
  const yAxis=f=>({beginAtZero:true,grid:{color:T.line},border:{display:false},ticks:{display:!narrow,maxTicksLimit:5,callback:v=>f(v)}});
  const tipW={callbacks:{label:c=>` ${c.dataset.label||c.label}: ${won(c.parsed.y??c.parsed)}`}};
  const leg={position:'bottom',labels:{usePointStyle:true,pointStyle:'circle',boxWidth:8,padding:16}};
  const hl=x=>fq!=='all'&&x===fq;
  const lineDs=k=>cd.series.map(s=>{const c=colorOf(s.color_index);return{label:s.branch,data:s[k],borderColor:c,backgroundColor:c,borderWidth:2,tension:.25,spanGaps:true,
    pointRadius:q.map(x=>hl(x)?6:4),pointHoverRadius:7,pointBorderColor:T.bg,pointBorderWidth:2}});
  const common={responsive:true,maintainAspectRatio:false,animation:{duration:matchMedia('(prefers-reduced-motion: reduce)').matches?0:400},interaction:{mode:'index',intersect:false}};
  draw('cLine',{type:'line',data:{labels:q,datasets:lineDs('amount')},options:{...common,plugins:{legend:leg,tooltip:tipW},scales:{x:{grid:{display:false}},y:yAxis(v=>short(v))}}});
  draw('cArpu',{type:'line',data:{labels:q,datasets:lineDs('arpu')},options:{...common,plugins:{legend:leg,tooltip:tipW},scales:{x:{grid:{display:false}},y:{...yAxis(v=>Math.round(v).toLocaleString('ko-KR')),beginAtZero:false}}}});
  const bq=cd.bar.quarter,bi=cd.bar.items;$('#barSub').textContent=bq?`${bq} · 단위 원`:'데이터 없음';
  if(bq&&$('#barQ').value!==bq)$('#barQ').value=bq;
  draw('cBar',{type:'bar',data:{labels:bi.map(r=>r.branch),datasets:[{label:'매출',data:bi.map(r=>r.amount),backgroundColor:bi.map(r=>colorOf(r.color_index)),borderRadius:{topLeft:4,topRight:4},borderSkipped:'bottom',maxBarThickness:56}]},
    options:{...common,interaction:{mode:'nearest',intersect:false,axis:'x'},plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>` 매출: ${won(c.parsed.y)}`}}},scales:{x:{grid:{display:false}},y:yAxis(v=>short(v))}}});
  const di=cd.donut.items,tot=di.reduce((s,x)=>s+x.customers,0);
  $('#donutSub').textContent=`${cd.donut.scope==='전체 분기'?'전체 분기 합계':cd.donut.scope} · 총 ${ppl(tot)}`;
  draw('cDonut',{type:'doughnut',data:{labels:di.map(x=>x.branch),datasets:[{data:di.map(x=>x.customers),backgroundColor:di.map(x=>colorOf(x.color_index)),borderColor:T.bg,borderWidth:2,hoverOffset:6}]},
    options:{responsive:true,maintainAspectRatio:false,cutout:'62%',animation:common.animation,plugins:{legend:leg,tooltip:{callbacks:{label:c=>` ${c.label}: ${ppl(c.parsed)} (${(c.parsed/tot*100).toFixed(1)}%)`}}}}});
}
function renderData(){renderCards();renderTable();renderCharts()}

/* ---------- 필터·정렬 ---------- */
const reload=async()=>{try{if(await loadData())renderData()}catch(e){if(e.status!==0)msg($('#tblMsg'),e.message)}};
$('#fQ').addEventListener('change',()=>{const v=$('#fQ').value;view.fq=v;if(v!=='all'){view.barQ=v;$('#barQ').value=v}saveView();reload()});
$('#barQ').addEventListener('change',async()=>{view.barQ=$('#barQ').value;saveView();
  try{D.chart=await api('GET','/api/chart-data'+qs({bar_quarter:view.barQ}));renderCharts()}catch(e){if(e.status!==0)msg($('#tblMsg'),e.message)}});
$('#fB').addEventListener('change',e=>{const b=e.target.value;view.off=e.target.checked?view.off.filter(x=>x!==b):[...view.off,b];saveView();reload()});
document.querySelectorAll('#tbl th[data-k]').forEach(th=>th.addEventListener('click',()=>{const k=th.dataset.k;sort=sort.k===k?{k,dir:-sort.dir}:{k,dir:1};renderTable()}));

/* ---------- 입력 ---------- */
$('#addForm').addEventListener('submit',async e=>{e.preventDefault();
  const {e:er,row}=check($('#iQ').value,$('#iB').value,$('#iA').value,$('#iC').value);
  if(er.length)return msg($('#addMsg'),er.join(' · '));
  try{const r=await api('POST','/api/sales',row);
    msg($('#addMsg'),r.action==='update'?`${r.row.quarter} ${r.row.branch} 데이터를 새 값으로 바꿨습니다.`:`${r.row.quarter} ${r.row.branch} 데이터를 추가했습니다.`,true);
    $('#iA').value='';$('#iC').value='';$('#iB').focus();await refresh()}
  catch(err){msg($('#addMsg'),err.message)}});

$('#csvBtn').addEventListener('click',async()=>{const el=$('#csvMsg'),file=$('#csvFile').files[0];let body;
  if(file){if(file.size>1048576)return msg(el,'파일은 1MB 이하만 올릴 수 있습니다.');body=new FormData();body.append('file',file)}
  else{const t=$('#csv').value;if(!t.trim())return msg(el,'붙여넣은 내용이 없습니다.');body={csv:t}}
  const btn=$('#csvBtn');btn.disabled=true;
  try{const r=await api('POST','/api/sales/import',body),n=r.added+r.updated,bad=r.skipped;
    msg(el,`${n}건 반영했습니다.`+(r.updated?` (추가 ${r.added}, 값 갱신 ${r.updated})`:'')+(bad.length?` 건너뛴 줄 ${bad.length}개 — ${bad.slice(0,3).map(s=>`${s.line}행: ${s.error}`).join(' / ')}${bad.length>3?' …':''}`:''),!bad.length);
    if(n&&!bad.length){$('#csv').value='';$('#csvFile').value=''}
    if(n)await refresh()}
  catch(err){msg(el,err.message)}finally{btn.disabled=false}});

/* ---------- 표: 수정·삭제 ---------- */
$('#tbl tbody').addEventListener('click',async e=>{const btn=e.target.closest('button');if(!btn)return;const id=+btn.closest('tr').dataset.id,a=btn.dataset.a;
  if(a==='edit'){editId=id;renderTable();$('#eA').focus()}
  else if(a==='cancel'){editId=null;renderTable()}
  else if(a==='del'){btn.disabled=true;
    try{await api('DELETE',`/api/sales/${id}`);if(editId===id)editId=null;msg($('#tblMsg'),'삭제했습니다. 되돌리기로 복구할 수 있습니다.',true);await refresh()}
    catch(err){btn.disabled=false;msg($('#tblMsg'),err.message)}}
  else if(a==='ok'){const {e:er,row}=check($('#eQ').value,$('#eB').value,$('#eA').value,$('#eC').value);
    if(er.length)return msg($('#tblMsg'),'수정 오류: '+er.join(' · '));
    try{await api('PUT',`/api/sales/${id}`,row);editId=null;msg($('#tblMsg'),`${row.quarter} ${row.branch} 데이터를 수정했습니다.`,true);await refresh()}
    catch(err){msg($('#tblMsg'),(err.status===409?'':'수정 오류: ')+err.message)}}});
$('#tbl tbody').addEventListener('keydown',e=>{if(e.target.tagName==='INPUT'&&e.key==='Enter')e.target.closest('tr').querySelector('[data-a=ok]').click();if(e.key==='Escape'){editId=null;renderTable()}});

/* ---------- 예시 지우기·초기화·되돌리기·내보내기 ---------- */
const twoStep=(btn,label,fn)=>{let armed=null;btn.addEventListener('click',()=>{if(armed){clearTimeout(armed);armed=null;btn.textContent=label;fn();return}
  btn.textContent='한 번 더 누르면 실행됩니다';armed=setTimeout(()=>{armed=null;btn.textContent=label},3000)})};
twoStep($('#clrSample'),'예시 데이터 지우기',async()=>{
  try{const r=await api('DELETE','/api/sales/sample');editId=null;msg($('#tblMsg'),`예시 데이터 ${r.deleted}건을 지웠습니다.`,true);await refresh()}
  catch(err){msg($('#tblMsg'),err.message)}});
$('#resetAll').addEventListener('click',async()=>{
  if(!confirm('모든 매출 데이터를 삭제합니다. 계속할까요?\n(실수했다면 "되돌리기"로 복구할 수 있습니다)'))return;
  try{await api('POST','/api/reset',{confirm:'RESET'});editId=null;msg($('#tblMsg'),'데이터를 모두 지웠습니다.',true);await refresh()}
  catch(err){msg($('#tblMsg'),err.message)}});
$('#undoBtn').addEventListener('click',async()=>{
  try{const r=await api('POST','/api/undo');editId=null;msg($('#tblMsg'),`되돌렸습니다 (${ACTION_LABEL[r.action]||r.action} 이전 상태).`,true);await refresh()}
  catch(err){msg($('#tblMsg'),err.message);refresh()}});
$('#expCsv').addEventListener('click',()=>{location.href='/api/export.csv'+qs()});
$('#expXlsx').addEventListener('click',()=>{location.href='/api/export.xlsx'+qs()});

/* ---------- 테마·크기 변경 ---------- */
const reTheme=()=>{renderFilters();renderTable();renderCharts()};
new MutationObserver(reTheme).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
matchMedia('(prefers-color-scheme: dark)').addEventListener('change',reTheme);
let rz;addEventListener('resize',()=>{clearTimeout(rz);rz=setTimeout(renderCharts,200)});

refresh();
})();
