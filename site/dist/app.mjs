import {calculate} from "./model.mjs";
const $=id=>document.getElementById(id);
const labels={manufacturing:"Manufacturing",construction:"Construction",real_estate:"Real estate",other:"Remaining industries"};
const money=x=>"€"+(x/1e6).toLocaleString("en-GB",{minimumFractionDigits:1,maximumFractionDigits:1})+"m";
const pct=x=>(100*x).toFixed(2)+"%";
let data, current, options, defaults;
function render(){
 options={pd:Number($("pd").value)/100,lgd:Number($("lgd").value)/100,severity:Number($("severity").value)/100};
 current=calculate(data.exposures,data.scenario,options);
 const t=current.totals, ordered=[...current.rows].sort((a,b)=>b.change-a.change);
 $("pdValue").textContent=pct(options.pd); $("lgdValue").textContent=(options.lgd*100).toFixed(0)+"%"; $("severityValue").textContent=(options.severity*100).toFixed(0)+"%";
 $("exposure").textContent="€"+(t.exposure/1e9).toFixed(3)+"bn observed lending";
 $("baseline").textContent=money(t.baseline); $("adverse").textContent=money(t.adverse); $("change").textContent=(t.change>=0?"+":"−")+money(Math.abs(t.change));
 $("baselineRate").textContent=pct(t.exposure?t.baseline/t.exposure:0)+" of exposure";
 $("adverseRate").textContent=pct(t.exposure?t.adverse/t.exposure:0)+" of exposure";
 $("multiple").textContent=t.baseline?(t.adverse/t.baseline).toFixed(2)+"× baseline":"Baseline multiple undefined";
 const max=Math.max(...ordered.map(r=>Math.max(r.baseline,r.adverse)),1);
 $("bars").replaceChildren();
 for(const r of ordered){
   const group=document.createElement("div"); group.className="bar-group";
   const label=document.createElement("div");label.className="bar-label";
   const name=document.createElement("strong"); name.textContent=labels[r.sector]||r.sector;
   const change=document.createElement("span");change.textContent="Change "+money(r.change);
   label.append(name,change);group.append(label);
   for(const type of ["baseline","adverse"]){const track=document.createElement("div");track.className="bar-track";const fill=document.createElement("div");fill.className="bar-fill "+(type==="adverse"?"adverse":"");fill.style.width=(r[type]/max*100)+"%";track.title=type+": "+money(r[type]);fill.setAttribute("aria-label",(labels[r.sector]||r.sector)+" "+type+" "+money(r[type]));track.append(fill);group.append(track);}
   $("bars").append(group);
 }
 $("driver").textContent=t.change>0?(labels[ordered[0].sector]||ordered[0].sector)+" contributes "+(100*ordered[0].change/t.change).toFixed(1)+"% of the loss increase under these assumptions.":"No portfolio loss increase under these assumptions.";
 $("caps").textContent="100% caps applied: "+t.pdCaps+" industry PDs; "+t.lgdCaps+" industry LGDs. Exposures remain fixed.";
 $("rows").replaceChildren();
 for(const r of current.rows){const tr=document.createElement("tr");const vals=[labels[r.sector]||r.sector,(r.exposure/1e9).toFixed(3),pct(r.adversePd)+(r.pdCapped?" *":""),pct(r.adverseLgd)+(r.lgdCapped?" *":""),(r.baseline/1e6).toFixed(1),(r.adverse/1e6).toFixed(1),(r.change/1e6).toFixed(1)]; vals.forEach((v,i)=>{const td=document.createElement(i===0?"th":"td");if(i===0)td.scope="row";td.textContent=v;tr.append(td);});$("rows").append(tr);}
}
function download(kind){const payload={purpose:"Illustrative scenario loss proxy; assumptions are not estimated",reference_date:data.reference_date,assumptions:options,scenario:data.scenario,exposures:data.exposures,...current};
 let text=JSON.stringify(payload,null,2), mime="application/json";
 if(kind==="csv"){const fields=Object.keys(current.rows[0]);text=fields.join(",")+"\n"+current.rows.map(r=>fields.map(f=>JSON.stringify(r[f])).join(",")).join("\n");text="# Reference date: "+data.reference_date+"; assumed baseline PD="+options.pd+"; assumed LGD="+options.lgd+"; severity="+options.severity+"\n"+text;mime="text/csv";}
 const url=URL.createObjectURL(new Blob([text],{type:mime})); const a=document.createElement("a");a.href=url;a.download="finnish-credit-scenario."+kind;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
try{const response=await fetch("./data.json");if(!response.ok)throw new Error("Data request failed");data=await response.json();const first=data.scenario.sectors[data.exposures[0].sector];defaults={pd:first.baseline_pd*100,lgd:first.baseline_lgd*100};$("pd").value=defaults.pd;$("lgd").value=defaults.lgd;render();for(const id of ["pd","lgd","severity"])$(id).addEventListener("input",render);$("reset").addEventListener("click",()=>{$("pd").value=defaults.pd;$("lgd").value=defaults.lgd;$("severity").value=100;render();});$("csv").addEventListener("click",()=>download("csv"));$("json").addEventListener("click",()=>download("json"));$("workspace").hidden=false;}
catch(e){$("error").hidden=false;$("error").textContent="The scenario could not load. Please reload the page or read the linked notebook.";console.error(e);}
