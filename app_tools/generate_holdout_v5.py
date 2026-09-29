"""Generate the versioned holdout frozen before Task 11 repair."""
from __future__ import annotations

import hashlib, json
from pathlib import Path
from reportlab.lib.colors import Color
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "evaluation-v5"
W, H = 612, 792

def box(x0,y0,x1,y1): return [round(x0/W,4),round(1-y1/H,4),round(x1/W,4),round(1-y0/H,4)]
def text_box(s,x,y,size=11): return box(x-2,y-3,x+stringWidth(s,"Helvetica",size)+2,y+10)
def sig(c,rgb):
    c.setFillColor(Color(*(v/255 for v in rgb))); c.rect(0,762,30,30,fill=1,stroke=0); c.rect(582,0,30,30,fill=1,stroke=0); c.setFillColorRGB(0,0,0)
def q(i,k,p,s,primary=None,regions=None):
    d={"id":i,"type":k,"question":p,"expected_page":list(s) if k!="absent" else None,"expected_region":primary}
    if regions:d["expected_regions"]=regions
    return d

def build():
    OUT.mkdir(parents=True,exist_ok=True); pdf=OUT/"holdout.pdf"; suite_path=OUT/"suite.json"; suite=[]
    red,green,gold=(205,55,45),(20,140,90),(210,150,20); c=canvas.Canvas(str(pdf),pagesize=(W,H),pageCompression=1)
    sig(c,red); c.setFont("Helvetica-Bold",17); c.drawString(72,720,"Valve commissioning record"); c.setFont("Helvetica",11)
    lines=[("t01","Where is the drawing revision listed?",680,"Drawing revision: D-14"),("t02","Where is the control state stated?",655,"Control state: automatic"),("t03","Where is the inspection period specified?",630,"Inspection period: 18 months"),("t04","Where is the caution statement?",605,"Caution: close supply before adjustment")]
    for i,p,y,s in lines:c.drawString(72,y,s);suite.append(q(i,"text",p,red,text_box(s,72,y)))
    c.setFont("Helvetica-Bold",11); c.drawString(84,560,"Parameter"); c.drawString(330,560,"Value"); c.drawString(448,560,"Unit"); c.setFont("Helvetica",11)
    rows=[("b01","Where is the nominal voltage row?",525,"Nominal voltage","48","V"),("b02","Where is the cable reach row?",495,"Cable reach","6.5","m"),("b03","Where is the trip current row?",465,"Trip current","12","A"),("b04","Where is the pressure limit row?",435,"Pressure limit","320","kPa")]
    for i,p,y,label,value,unit in rows:
        c.rect(72,y-8,480,24,fill=0,stroke=1);c.drawString(84,y,label);c.drawString(330,y,value);c.drawString(448,y,unit);row=box(80,y-5,480,y+12);suite.append(q(i,"table",p,red,row,[row,text_box(unit,448,y)]))
    c.showPage()
    sig(c,green);c.setFont("Helvetica-Bold",17);c.drawString(72,720,"Fan output profile");c.rect(90,390,420,230,fill=0,stroke=1);c.setFont("Helvetica",11);c.drawString(90,637,"Output (L/s)");c.drawString(284,356,"Speed (%)");c.drawString(90,375,"0");c.drawString(488,375,"100");c.drawString(525,570,"rated")
    c.setStrokeColorRGB(0,.45,.25);c.setLineWidth(3);p=c.beginPath();p.moveTo(110,570);p.curveTo(230,565,350,500,485,415);c.drawPath(p,fill=0,stroke=1);c.setStrokeColorRGB(0,0,0);c.setLineWidth(1)
    chart=box(90,390,510,620);legend=text_box("rated",525,570);axis=text_box("Speed (%)",284,356)
    suite += [q("v01","visual","Where does rated output decline at high speed?",green,box(90,345,595,620),[chart,legend,axis]),q("v02","visual","Where does the rated curve begin at low speed?",green,box(90,345,345,620),[box(90,390,300,620),axis]),q("v03","visual","Where is the rated legend relative to the curve?",green,box(90,390,595,620),[chart,legend])]
    c.drawString(120,300,"Inlet");c.rect(115,165,145,120,fill=0,stroke=1);c.drawString(350,300,"Fan");c.circle(395,225,65,fill=0,stroke=1);suite.append(q("v04","visual","Where is the fan relative to the inlet?",green,box(110,160,465,315)));c.showPage()
    sig(c,gold);c.setFont("Helvetica-Bold",17);c.drawString(72,720,"Dual contactor enclosure");c.setFont("Helvetica",12);c.drawString(72,660,"Sector East");c.drawString(330,660,"Sector West");c.rect(72,455,210,170,fill=0,stroke=1);c.rect(330,455,210,170,fill=0,stroke=1)
    for x in (72,330):c.drawString(x+34,570,"K3 contactor");c.rect(x+60,515,58,32,fill=0,stroke=1);c.circle(x+170,500,15,fill=0,stroke=1);c.drawString(x+130,470,"anchor stud")
    east,west=box(72,455,282,625),box(330,455,540,625);eh,wh=text_box("Sector East",72,660,12),text_box("Sector West",330,660,12)
    suite += [q("v05","visual","Where is the K3 contactor in Sector East?",gold,box(72,455,282,674),[eh,east]),q("v06","visual","Where is the K3 contactor in Sector West?",gold,box(330,455,540,674),[wh,west]),q("v07","visual","Where is the anchor stud relative to K3 in Sector East?",gold,box(72,455,282,674),[eh,east]),q("v08","visual","Where is the outlined enclosure boundary for Sector West?",gold,box(330,455,540,674),[wh,west])];c.showPage();c.save()
    for i,p in [("a01","Where is the emergency drain pedal?"),("a02","Where is the battery level meter?"),("a03","Where is the K9 contactor in Sector East?"),("a04","Where is the remote bypass selector?")]:suite.append(q(i,"absent",p,red))
    assert len(suite)==20; suite_path.write_text(json.dumps(suite,indent=2)+"\n",encoding="utf-8");m={"pdf_sha256":hashlib.sha256(pdf.read_bytes()).hexdigest(),"suite_sha256":hashlib.sha256(suite_path.read_bytes()).hexdigest(),"question_count":20,"split":[4,4,8,4],"purpose":"fresh synthetic quality holdout; frozen before Task 11 repair"};(OUT/"manifest.json").write_text(json.dumps(m,indent=2)+"\n",encoding="utf-8");return pdf,suite_path
if __name__=="__main__":print(*build(),sep="\n")
