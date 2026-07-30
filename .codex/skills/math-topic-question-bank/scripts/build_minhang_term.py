import yaml

from question_bank_repo import find_repo_root


R = find_repo_root()
PID="2026-MINHANG-TERM"
SRC="documents/初三/闵行区-2025学年第一学期初三年级学业质量调研-数学-试卷及参考答案"
OUT=R/"artifacts/题库/2026-07-24-上海初三试卷原题库/staging"/PID
Z="sha256:"+"0"*64

data=[
(1,"choice",4,"下列各组图形中不一定是相似形的是",["两个等腰直角三角形","两个等边三角形","两个正方形","两个直角三角形"],"D"),
(2,"choice",4,"下列函数中，二次函数是",["$y=3$","$y=\\frac1x$","$y=x(2x-1)$","$y=(x+4)^2-x^2$"],"C"),
(3,"choice",4,"下列关于向量的说法中，一定正确的是",["若 $\\vec b=-2\\vec a$，则 $\\vec a\\parallel\\vec b$","若 $\\vec e$ 是单位向量，则 $\\vec e=1$","向量 $\\overrightarrow{AB}$ 与 $\\overrightarrow{BA}$ 是相同向量","若 $\\vec a=\\vec0$，则对任意实数 $k$ 有 $k\\vec a=0$"],"A"),
(4,"choice",4,"如图，直线 $h$ 与 $\\triangle ABC$ 的边 $AB,AC$ 分别交于 $D,E$，过 $D,E$ 分别作平行于 $BC$ 的直线，交于图中各点。下列比例式一定正确的是",["$\\frac{DE}{DF}=\\frac{EF}{GF}$","$\\frac{DE}{BF}=\\frac{EF}{GC}$","$\\frac{DE}{FG}=\\frac{EF}{BC}$","$\\frac{DE}{BF}=\\frac{FG}{EG}$"],"B"),
(5,"choice",4,"抛物线 $y=ax^2+bx+c$（$a<0$）的对称轴是 $x=1$，且与 $x$ 轴有两个交点，下列结论一定正确的是",["$c<0$","$b<0$","$2a+b=0$","$a+b+c=0$"],"C"),
(6,"choice",4,"如图，抛物线 $C_1:y=x^2-6x$ 向右平移得到 $C_2,C_3$，三条抛物线与直线 $y=m$ 分别交于两点。六个交点横坐标之和是",["$6$","$18$","$30$","$54$"],"D"),
(7,"fillin",4,"如果 $\\frac a2=\\frac b3$，那么 $\\frac{b-a}{a}$ 的值是\\fillin。",None,"$\\frac12$"),
(8,"fillin",4,"计算：$2(3\\vec a-\\vec b)+3\\vec b=$\\fillin。",None,"$6\\vec a+\\vec b$"),
(9,"fillin",4,"如果两个相似三角形的面积比为 $16:9$，那么它们的周长比是\\fillin。",None,"$4:3$"),
(10,"fillin",4,"长方形的长是 $x$，宽是长的一半，面积是 $y$，那么 $y$ 关于 $x$ 的解析式是\\fillin。",None,"$y=\\frac12x^2$"),
(11,"fillin",4,"在 $\\mathrm{Rt}\\triangle ABC$ 中，$\\angle C=90^\\circ,BC=12,\\sin B=\\frac34$，那么 $AB$ 的长是\\fillin。",None,"$16$"),
(12,"fillin",4,"如图，传送带和地面所成斜坡的坡度为 $1:2$，把物体送到离地面 $4$ 米高处，物体经过的路程是\\fillin米。",None,"$4\\sqrt5$"),
(13,"fillin",4,"在 $\\triangle ABC$ 中，点 $D,E$ 分别是 $AB,AC$ 的黄金分割点，且 $AD>DB,AE>EC,BC=2$，那么 $DE$ 的长是\\fillin。",None,"$\\sqrt5-1$"),
(14,"fillin",4,"在 $\\mathrm{Rt}\\triangle ABC$ 中，$\\angle C=90^\\circ,\\angle ABC=60^\\circ,AB=12$，结合图中的尺规作图痕迹，$AD$ 的长是\\fillin。",None,"$6$"),
(15,"fillin",4,"如图，手距墙壁 $3$ 米，光源与手的距离为 $1$ 米。手的位置不变，光源与手的距离增加 $1$ 米后，手影长度与原手影长度的比值是\\fillin。",None,"$\\frac58$"),
(16,"fillin",4,"如图，在 $\\triangle ABC$ 中，$M,N$ 分别是 $AB,BC$ 的中点，$AN,CM$ 交于 $G$，$GF\\parallel AC$ 交 $BC$ 于 $F$，那么 $S_{\\triangle GNF}:S_{\\triangle GAC}=$\\fillin。",None,"$\\frac16$"),
(17,"fillin",4,"如图，在 $\\triangle ABC$ 中，$AB=AC,AC=10,\\cos A=\\frac45$。点 $D$ 在 $BC$ 上，且 $\\angle ADB=90^\\circ+\\angle BAD$，那么 $AD=$\\fillin。",None,"$3\\sqrt5$"),
(18,"fillin",4,"如图，在矩形 $ABCD$ 中，$E$ 是 $BC$ 中点，过 $E$ 作 $EF\\parallel BD$ 交 $CD$ 于 $F$，将 $\\triangle CEF$ 沿 $EF$ 翻折到 $\\triangle GEF$，若 $G$ 在 $AE$ 上，那么 $BG:AE=$\\fillin。",None,"$\\frac{2\\sqrt3}{9}$"),
(19,"problem",10,"计算：$\\sin45^\\circ-2\\sin60^\\circ+\\frac{2\\tan45^\\circ}{\\tan60^\\circ+1}$。",None,"$\\frac{\\sqrt2}{2}-1$"),
(20,"problem",10,"如图，在平行四边形 $ABCD$ 中，$E$ 是 $DC$ 中点，$AE$ 与对角线 $BD$ 交于 $G$，$\\overrightarrow{AB}=\\vec a,\\overrightarrow{AD}=\\vec b$。（1）用 $\\vec a,\\vec b$ 表示 $\\overrightarrow{DB},\\overrightarrow{AG}$；（2）作出 $\\overrightarrow{DG}$ 在 $\\vec a,\\vec b$ 方向上的分向量。",None,"$\\overrightarrow{DB}=\\vec a-\\vec b,\\overrightarrow{AG}=\\frac13\\vec a+\\frac23\\vec b$；作图略"),
(21,"problem",10,"表一给出送餐机器人对地面压强 $p$ 与接触面积 $S$ 的反比例关系，表二给出不同地面材料可承受的最大压强。（1）求 $p$ 关于 $S$ 的函数表达式；（2）为确保在各种地面上均不造成破坏，求接触面积至少为多少平方米。",None,"（1）$p=\\frac{48}{S}$；（2）$2\\times10^{-6}\\,\\mathrm m^2$"),
(22,"problem",12,"如图，线段 $AD,BC$ 交于点 $E$，$F$ 是 $ED$ 中点，联结 $AB,BD,CD$，延长 $BA,FC$ 交于 $G$。已知 $\\angle BAD=90^\\circ,\\frac{AE}{CE}=\\frac{BE}{DE}$。（1）证明 $\\angle ABE=\\angle FCD$；（2）若 $DA$ 平分 $\\angle BDC$，证明 $\\frac{BG}{BD}=\\frac{BC}{2CF}$。",None,"两问结论成立"),
(23,"problem",10,"探究活动：巧拼地砖外边。根据图示条形边角料的拼接、画线和切割操作：（1）补全操作过程图并标注字母；（2）大、小边角料宽分别为 $12\\rm cm,9\\rm cm$，求 $\\tan\\angle OCP$；（3）设计一种新裁剪方案并说明理由。",None,"（1）见图；（2）$\\frac34$；（3）可将两条边角料都沿 $OA$ 切割"),
(24,"problem",12,"如图，抛物线 $C_1:y=-\\frac12x^2+bx+c$ 经过 $A(5,-6)$，对称轴为 $x=1$，顶点为 $D$。（1）求表达式及 $D$；（2）点 $M$ 在 $C_1$ 上，过 $M$ 作 $x=m$，当 $M$ 在对称轴右侧时，抛物线在直线右侧部分的最高点纵坐标为 $2-m$，求 $m$；（3）按题设构造点 $P,Q$，当顶点 $D$ 在 $\\triangle PQM$ 内部时，写出 $m$ 的范围。",None,"（1）$y=-\\frac12x^2+x+\\frac32,D(1,2)$；（2）$m=2+\\sqrt3$；（3）$-3<m<1-\\sqrt6$ 或 $m>1+\\sqrt6$"),
(25,"problem",14,"如图，在 $\\triangle ABC$ 中，点 $D$ 在 $AC$ 上。（1）当 $\\angle ABC=90^\\circ$：①若 $BD\\perp AC$，证明 $BD^2=AD\\cdot CD$；②按图2条件求 $\\cot C$。（2）按图3条件作点 $G,E,O$，求题设两三角形面积之比。",None,"（1）①结论成立；②$\\cot C=\\frac34$；（2）$2-\\sqrt2$"),
]

qboxes={
1:[(2,[150,520,960,625])],2:[(2,[150,615,960,710])],3:[(2,[150,700,960,885])],4:[(2,[150,860,960,1025])],5:[(2,[150,1010,960,1120])],6:[(2,[150,1100,960,1370])],
7:[(3,[150,235,960,300])],8:[(3,[150,285,960,340])],9:[(3,[150,325,960,375])],10:[(3,[150,355,960,440])],11:[(3,[150,420,960,485])],12:[(3,[150,465,960,540])],13:[(3,[150,525,960,600])],14:[(3,[150,585,960,820])],15:[(3,[150,790,960,950])],16:[(3,[150,920,960,1020])],17:[(3,[150,1000,960,1095])],18:[(3,[150,1070,960,1360])],
19:[(4,[150,225,960,390])],20:[(4,[150,370,960,820])],21:[(4,[150,805,960,1350])],22:[(5,[150,165,960,640])],23:[(5,[150,635,960,1500]),(6,[150,100,960,1360])],24:[(7,[150,165,960,1330])],25:[(8,[150,165,960,1330])]}
prompts={
4:[(2,[570,740,940,1010])],6:[(2,[560,1070,950,1360])],12:[(3,[675,145,950,300])],14:[(3,[155,620,585,815])],15:[(3,[555,620,950,815])],16:[(3,[130,1120,390,1340])],17:[(3,[385,1110,650,1340])],18:[(3,[645,1100,965,1340])],
20:[(4,[560,500,940,790])],21:[(4,[180,1000,950,1240])],22:[(5,[590,175,950,620])],23:[(5,[160,680,950,1000]),(6,[160,100,950,570]),(6,[160,1010,950,1325])],24:[(7,[500,700,940,1050])],25:[(8,[150,700,960,1000])]}
official={**{i:[(9,[145,230,955,520])] for i in range(1,19)},19:[(9,[145,515,955,720])],20:[(9,[145,710,955,900])],21:[(9,[145,875,955,1410])],22:[(10,[145,110,955,1120])],23:[(10,[145,1080,955,1500]),(11,[145,100,955,500])],24:[(11,[145,480,955,1135])],25:[(11,[145,1120,955,1510]),(12,[145,100,955,1500]),(13,[145,100,955,1420])]}
solutions={23:[(10,[180,1120,620,1480])],25:[(13,[520,420,950,1120])]}

def pg(n): return f"{SRC}/{n:03d}.png"
def cr(p,b,o): return {"source":pg(p),"source_sha256":Z,"box_px":b,"whiteout_px":[],"output":o,"output_sha256":Z}
def sec(n): return "一、选择题" if n<7 else ("二、填空题" if n<19 else "三、解答题")
OUT.mkdir(parents=True,exist_ok=True)
paper={"schema":"math_exam_paper/v1","paper":{"id":PID,"title":"2025学年第一学期初三年级学业质量调研数学试卷","grade":"九年级","subject":"数学","source_archive":SRC},"question_bank":"../../question-bank.yaml","sections":[{"id":"choice","title":"一、选择题","item_ids":[f"Q{i:03d}" for i in range(1,7)]},{"id":"fillin","title":"二、填空题","item_ids":[f"Q{i:03d}" for i in range(7,19)]},{"id":"problem","title":"三、解答题","item_ids":[f"Q{i:03d}" for i in range(19,26)]}]}
(OUT/"paper.yaml").write_text(yaml.safe_dump(paper,allow_unicode=True,sort_keys=False))
maps=[]
for n,qt,pts,stem,chs,ans in data:
 qs=[]; os=[]
 for p,_ in qboxes[n]:
  if pg(p) not in qs: qs.append(pg(p))
 for p,_ in official[n]:
  if pg(p) not in os: os.append(pg(p))
 maps.append({"item_id":f"Q{n:03d}","question_number":n,"question_pages":qs,"official_solution":{"pages":os,"start_anchor":f"{n}.","end_anchor":"<END_OF_SOURCE>" if n==25 else f"{n+1}."}})
(OUT/"paper-map.yaml").write_text(yaml.safe_dump({"schema":"math_exam_paper_map/v1","paper_id":PID,"items":maps},allow_unicode=True,sort_keys=False))
for n,qt,pts,stem,chs,ans in data:
 iid=f"Q{n:03d}"; d=OUT/"items"/iid; (d/"assets").mkdir(parents=True,exist_ok=True)
 qe=[cr(p,b,f"assets/source-question-{j:02d}.png") for j,(p,b) in enumerate(qboxes[n],1)]
 pr=[cr(p,b,f"assets/prompt-{j:02d}.png") for j,(p,b) in enumerate(prompts.get(n,[]),1)]
 so=[cr(p,b,f"assets/solution-{j:02d}.png") for j,(p,b) in enumerate(solutions.get(n,[]),1)]
 of=[cr(p,b,f"assets/official-solution-{j:02d}.png") for j,(p,b) in enumerate(official[n],1)]
 sy={"schema":"math_exam_item_source/v1","item_id":iid,"source_key":f"{PID}-Q{n}","paper_id":PID,"question_number":n,"question_type":qt,"points":pts,"section_title":sec(n),"source_directory":SRC,"crops":{"question_evidence":qe,"prompt":pr,"solution":so,"official_solution":of},"transcription":{"question_status":"author_pass","official_solution_status":"author_pass","independent_review":"pending","human_review":"pending","prompt_status":"needs_human_crop" if pr else "author_pass","prompt_review_notes":["当前一次裁切仅保留作答所需视觉对象；源页水印或密集排版使最佳边界不确定，建议人工复核。"] if pr else []},"content_hash":Z}
 (d/"source.yaml").write_text(yaml.safe_dump(sy,allow_unicode=True,sort_keys=False))
 b={"type":qt,"id":iid,"points":pts,"stem_latex":stem,"answer":ans}
 if chs:b["choices"]=chs
 if qt=="problem":
  step={"title":"解答","content":f"依据官方评分标准，答案为：{ans}。"}
  if so: step["diagram_col"]={"image_path":so[0]["output"],"width":"58mm","variant":"solution","disclosure_policy":"teacher_only"}
  b["solution_steps"]=[step]
 if pr:b["images"]=[{"image_path":x["output"],"width":"0.82\\linewidth","variant":"source_prompt","disclosure_policy":"always","label":f"原题配图{j}"} for j,x in enumerate(pr,1)]
 b["source_solution_images"]=[{"image_path":x["output"],"width":"0.96\\linewidth","variant":"source_solution","disclosure_policy":"teacher_only","label":f"官方原解答第{j}页"} for j,x in enumerate(of,1)]
 t={"meta":{"title":f"闵行区2025学年第一学期质量调研第{n}题","grade":"九年级","subject":"数学","total_points":pts,"version":"teacher","show_answers":True,"source_artifacts":{"source_record":"source.yaml"}},"render":{"template":"exam-zh-practice","paper_size":"a4paper","answer_key_position":"inline"},"sections":[{"id":"question","title":sec(n),"type":"practice","visibility":"both","blocks":[b]}]}
 (d/"teacher.resolved.assignment.yaml").write_text(yaml.safe_dump(t,allow_unicode=True,sort_keys=False))
print(OUT)
