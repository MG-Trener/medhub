// Local-only synthetic fixture. Never used by the application or deployment.
import http from 'node:http'
import { readFile } from 'node:fs/promises'
import { resolve, extname } from 'node:path'
const root = resolve(import.meta.dirname, '../dist')
const text = 'Синтетические данные для проверки интерфейса. Длинный текст, который должен оставаться доступным без прокрутки. '.repeat(35)
const patients = Array.from({ length: 23 }, (_, i) => ({ id: 'p'+i, name: i ? 'Тестовый Пациент '+i : 'Тестовый Пациент С Длинным Именем', birth_date:'1990-01-01',iin:'000000000000',phone:'',sex:'unknown',processing_consent:true,ai_processing_allowed:true,external_id:null }))
const fields = Object.fromEntries(['complaints','anamnesis','life_history','allergies','medications','chronic_conditions','family_history','operations','habits','examination','investigations','diagnosis','recommendations','follow_up','ai_test_recommendations','ai_diagnosis_variants'].map(k=>[k,text]))
Object.assign(fields,{visit_type:'primary',visit_format:'in_person',diagnosis_code:'',sources:[],reviewed_fields:[],warnings:[text],diagnosis_suggestions:[]})
let encounter = { id:'e0', patient_id:'p0', status:'draft', started_at:Date.now()/1000-40, created_at:Date.now()/1000-40, ended_at:null, version:1, persisted:true, can_edit:true, fields, physician_name:'Тестовый врач', speaker_roles:{SPEAKER_00:'doctor'}, transcript:Array.from({length:30},(_,i)=>({speaker:'SPEAKER_00',start:i*10,end:i*10+8,text})),redacted_transcript:[{speaker:'SPEAKER_00',start:0,end:8,text}],live_session:null }
const encounters = Array.from({length:21},(_,i)=>({...encounter,id:'e'+i,ended_at:i?Date.now()/1000:null,patient:patients[0]}))
const settings={llm_configured:true,asr_configured:true,asr_provider:'local',mis_configured:false,consent_signature_required:false}
const json=(res,data,status=200)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(data))}
http.createServer(async(req,res)=>{
 try{
 const url=new URL(req.url,'http://127.0.0.1'), path=url.pathname.replace('/api/v1','')
 if(url.pathname.startsWith('/api/')){
  let raw='';for await(const chunk of req)raw+=chunk;const body=raw?JSON.parse(raw):{}
  if(path==='/auth/me')return json(res,{id:'doctor',name:'Тестовый врач'})
  if(path==='/settings')return json(res,settings)
  if(path==='/patients')return json(res,patients.slice(Number(url.searchParams.get('offset')||0),Number(url.searchParams.get('offset')||0)+Number(url.searchParams.get('limit')||5)))
  if(/^\/patients\/[^/]+\/consents$/.test(path))return json(res,{policy:{signature_required:false,sigex_enabled:false},current:null,history:[]})
  if(/^\/patients\/[^/]+\/encounters$/.test(path))return json(res,encounters)
  if(/^\/patients\/[^/]+$/.test(path))return json(res,patients.find(p=>p.id===path.split('/').at(-1))||patients[0])
  if(path==='/encounters')return json(res,encounters.slice(Number(url.searchParams.get('offset')||0),Number(url.searchParams.get('offset')||0)+Number(url.searchParams.get('limit')||5)))
  if(/\/recordings$|\/history$/.test(path))return json(res,[])
  if(path==='/encounters/e0/finish'){encounter={...encounter,ended_at:Date.now()/1000,version:encounter.version+1};return json(res,encounter)}
  if(path==='/encounters/e0' && req.method==='PATCH'){encounter={...encounter,...body,version:encounter.version+1};return json(res,encounter)}
  if(/^\/encounters\/[^/]+$/.test(path))return json(res,encounter)
  if(path==='/diagnoses')return json(res,{version:'test',items:[]})
  return json(res,{detail:'Fixture route not implemented: '+path},404)
 }
 const file=resolve(root,'.'+decodeURIComponent(url.pathname==='/'?'/index.html':url.pathname))
 if(!file.startsWith(root))return json(res,{},403)
 const data=await readFile(file);res.writeHead(200,{'Content-Type':({'.html':'text/html','.js':'text/javascript','.css':'text/css','.png':'image/png','.ttf':'font/ttf'})[extname(file)]||'application/octet-stream'});res.end(data)
 }catch(e){json(res,{detail:e.message},500)}
}).listen(5180,'127.0.0.1',()=>console.log('Synthetic preview: http://127.0.0.1:5180'))
