"""Build the submission PDF from checked, sanitized evidence. Requires ReportLab."""
import hashlib
import json
from pathlib import Path
import subprocess
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
OUT=ROOT/'output/pdf/CampusClaw_项目与LLM链路验证报告.pdf'
D=json.loads((HERE/'llm-traces.json').read_text(encoding='utf-8'))
COMPOSE=json.loads((HERE/'compose-runtime.json').read_text(encoding='utf-8'))
CASES={c['id']:c for c in D['cases']}
LIVE={c['case']:c for c in D['real_llm_cases']}
REV=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
REPO=D['repository']
FONT=Path('C:/Windows/Fonts')
pdfmetrics.registerFont(TTFont('YaHei',str(FONT/'msyh.ttc'),subfontIndex=0))
pdfmetrics.registerFont(TTFont('YaHeiBold',str(FONT/'msyhbd.ttc'),subfontIndex=0))
BRICK=colors.HexColor('#963c30'); INK=colors.HexColor('#302720'); MUTED=colors.HexColor('#78675b')
LINE=colors.HexColor('#e4d5c9'); SOFT=colors.HexColor('#f6eee7')
B=ParagraphStyle('body',fontName='YaHei',fontSize=9.5,leading=16,spaceAfter=8,textColor=INK,wordWrap='CJK')
SM=ParagraphStyle('small',parent=B,fontSize=8,leading=12.5,spaceAfter=6)
H=ParagraphStyle('heading',parent=B,fontName='YaHeiBold',fontSize=20,leading=30,spaceAfter=15,textColor=BRICK)
SUB=ParagraphStyle('sub',parent=B,fontName='YaHeiBold',fontSize=12,leading=20,spaceBefore=9,spaceAfter=7,textColor=BRICK)
CODE=ParagraphStyle('code',parent=B,fontSize=8,leading=12,backColor=SOFT,borderPadding=8,spaceBefore=4,spaceAfter=10)
CELL=ParagraphStyle('cell',parent=SM,spaceAfter=0)
story=[]

def p(s,style=B): story.append(Paragraph(escape(str(s)).replace('\n','<br/>'),style))
def rich(s,style=B): story.append(Paragraph(s,style))
def h(s): p(s,SUB)
def page(n,title):
    if story: story.append(PageBreak())
    p(f'{n:02}  /  {title}',H)
def code(value):
    text=json.dumps(value,ensure_ascii=False,indent=2) if not isinstance(value,str) else value
    p(text,CODE)
def table(headers,rows,widths):
    data=[[Paragraph(escape(str(x)),CELL) for x in row] for row in [headers,*rows]]
    t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),SOFT),('TEXTCOLOR',(0,0),(-1,0),BRICK),
        ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),
        ('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),
        ('LINEBELOW',(0,0),(-1,0),.8,LINE),('LINEBELOW',(0,1),(-1,-1),.35,LINE)]))
    story.extend([t,Spacer(1,9)])
def link(label,path):
    url=REPO+'/blob/'+REV+'/'+path
    rich(f'<link href="{escape(url)}" color="#963c30">{escape(label)}</link>',SM)
def answer(key): p(LIVE[key].get('assembled_answer','本轮未完成，见JSON证据。'),SM)
def meta(key): return CASES[key]['app_events'][0][1]

page(1,'个人项目应用平台')
p('CampusClaw',ParagraphStyle('cover',parent=H,fontSize=34,leading=46))
p('项目介绍与 LLM 请求链路验证报告',SUB)
p('提交人：gjj  |  验证日期：2026-10-26')
rich(f'Git 仓库：<link href="{REPO}" color="#963c30">{REPO}</link>')
p('CampusClaw 面向班级教学，教师配置应用、提示词、共享知识库、技能及MCP工具；学生在同一学习工作区提问，按需加入资料和技能，阅读引用并复用自己的个人资料。',B)
table(['要求','项目实现'],[
 ('多个 AI 应用','课程答疑、解题引导、学习计划；支持本班自定义助手。'),
 ('提示词模板','内置与自建模板；变量预览与角色快照应用。'),
 ('知识库检索','SQLite关键词与Qdrant向量混合检索、引用来源、分段与重建。'),
 ('Skill技能','内置技能安装、教师上传管理、提问时上传/指定私有技能。'),
 ('外部工具与MCP','同仓MCP服务器、握手发现、绑定、鉴权调用与审计。')],[110,405])
p('界面为暖色深浅主题，提供个人资料库和独立教师管理台。错题本、智能批改、自主学习模块不在本次范围内。',SM)
story.append(Image(str(HERE/'workspace.png'),width=515,height=290))
p('图1：实际学习工作区；技能、资料和上传入口位于提问框内。',SM)

page(2,'验证方法与结果边界')
p('采用源码追踪、隔离HTTP断言、真实模型固定请求重放和真实检索集成四层证据。所有输入为合成教学内容；请求和返回均脱敏，不公开密钥或供应商网关地址。')
table(['层次','方法与本轮结果'],[
 ('源码与回归','94项单元测试、30项HTTP接口用例、Node SSE测试通过；10个OpenSpec严格校验通过。'),
 ('隔离HTTP','真实应用处理器/临时数据库；模型HTTP替身及嵌入/向量替身，用于确定性断言传输和权限。'),
 ('真实模型','八组固定messages快照重放到配置网关；8/8完成，保留原始SSE与拼接正文，模型名course-chat。'),
 ('真实RAG集成','本机Python进程：真实2048维嵌入、专用临时Qdrant集合、检索、引用、SSE完成及落库一致性通过。'),
 ('真实MCP','Compose演示服务：initialize、tools/list、formula_hint、unit_convert；ok和断开后的denied审计通过。'),
 ('Docker限制','运行中的8000端口MCP正常；容器模型仍因TLS连接错误未完成。不能用本机进程通过代替容器通过。')],[95,420])
h('真实模型与可重复实验的区别')
p('真实模型重放使用每组固定messages，以便比较完全相同的输入。T02历史中的助手消息来自隔离测试，不会被前一组真实模型回复替换。真实RAG集成另行走实际应用发送、生成和落库链路。模型措辞不是固定预期，HTTP与引用检查也不等同于教学效果人工评审。')
h('证据文件')
p('llm-traces.json：cases为隔离HTTP实录；real_llm_cases为八组真实请求与返回；real_integration为真实RAG验收；mcp_rpc为真实RPC参数和result。compose-runtime.json单独记录Docker限制。',SM)
link('完整脱敏请求、SSE原文与断言证据','docs/verification/llm-traces.json')
link('实际Compose调用与审计证据','docs/verification/compose-runtime.json')

page(3,'验证1：每轮LLM参数与返回')
p('主对话发往 POST {CHAT_BASE_URL}/chat/completions。Authorization为模型网关密钥，仅从服务端环境读取；Content-Type为application/json，Accept为text/event-stream。以下为T01真实发送的完整JSON。')
code(LIVE['T01_template']['request'])
p('请求只包含model、messages、stream。未显式设置temperature、top_p、max_tokens、seed、tools或tool_choice；这些字段的缺省行为由网关/模型决定。不能把网页上的context对象当作发给模型的原始参数。',SM)
h('T01真实返回的完整拼接正文')
answer('T01_template')
p(f"HTTP {LIVE['T01_template'].get('response_status','未知')}；正文增量 {len(LIVE['T01_template']['response_chunks'])} 次；网关终止帧为finish_reason=stop及[DONE]。应用再输出meta、delta、done并保存完成状态。",SM)
link('序列化与SSE解析：gateway.py','campusclaw/gateway.py')

page(4,'验证1：模板与历史如何传递')
h('模板原文与变量')
code({'template':D['template']['raw'],'variables':D['template']['variables']})
h('实际渲染后保存的角色正文')
p(D['template']['rendered'],CODE)
p('结论：已应用模板的渲染正文每轮随system传入，并附加资料安全规则及适用Skill正文。未应用的模板不参与请求；模板名称、变量对象、完整模板库不会作为独立字段传给LLM。仅做预览也不会自动改变助手。')
h('历史输入')
table(['T01首轮','T02下一轮的消息顺序'],[
 ('system','system：当前有效角色、规则与本轮适用技能'),
 ('user','user：上轮已完成问题'),
 ('无历史','assistant：上轮已完成回答'),
 ('无历史','user：本轮新问题及重新组织的资料/工具数据')],[150,365])
p('TutorStore.history只取最近6条completed消息，按时间顺序放回，每条最多500字；failed/partial不进入历史。历史存的是问题/回答文本，不是上轮完整检索附件包。每轮重新读取角色与技能、重新检索知识和调用工具；模板编辑后不会追溯改写已经保存的角色快照。',SM)
link('模板渲染与保存快照：platform_store.py','campusclaw/platform_store.py')
link('消息历史与状态：tutor.py','campusclaw/tutor.py')

page(5,'验证2：知识库是否整库传入')
k=CASES['T03_knowledge']['checks']
p('结论：共享知识库采用检索增强，只发送检索命中的片段，不逐轮发送整个知识库。短文档可能恰好全部命中，此时“发送了全文”也不代表系统采用整库传输。')
table(['实测指标','T03结果'],[
 ('绑定文档长度',str(k['document_chars'])+'字'),('索引片段总数',str(k['indexed_chunks'])+'段'),
 ('传入模型片段',str(k['sent_chunks'])+'段，共'+str(k['sent_source_chars'])+'字'),
 ('文档尾部标记KB_TAIL_NOT_SENT','未出现在请求中'),('未绑定材料标记UNBOUND_MATERIAL_NOT_SENT','未出现在请求中')],[240,275])
table(['引用','原文位置 [start,end)','长度'],[(s['citation'],f"[{s['char_start']},{s['char_end']})",len(s['content'])) for s in meta('T03_knowledge')['sources']],[80,300,135])
h('主对话检索与拼接规则')
p('先按会话班级、绑定材料和ready的当前索引版本限定候选。关键词频次排名与向量排名采用RRF融合，主对话最多取4片段；默认绑定还按助手学科过滤，不保证补满4段。正文以[S1]等编号放在最后一条user消息中，system要求资料仅作数据并校验引用。')
h('需要区分的另一条路径')
p('个人资料与原会话附件由用户显式加入，采用正文全文注入user，并不走共享知识库检索。每轮最多3份资料；私有正文合计最多18000字。T06实测PERSONAL_BEGIN与PERSONAL_END均出现在user，而未出现在system。',SM)
link('片段检索、范围和索引版本：rag.py','campusclaw/rag.py')
link('证据拼接：orchestration.py；完整T03请求见JSON','campusclaw/orchestration.py')

page(6,'验证3：Skill是否传入全部内容')
p('结论：已绑定不等于每次执行。只有被自动路由命中或本轮显式指定的一个技能才参与。教师管理的共享技能传入完整body；文件头部不是整体发给LLM。')
h('上传的完整Skill文件（T04）')
p(D['skill_fixture']['file'],CODE)
h('进入system的完整技能正文')
p(D['skill_fixture']['parsed_body'],CODE)
table(['验证场景','结果'],[
 ('T04 命中共享技能','完整body和末尾SKILL_BODY_END进入system；名称/条件/开关/工具头部未整体进入。'),
 ('T05 绑定但无关键词匹配','没有SKILL_BODY_END；不注入此技能正文。'),
 ('T06 本轮私有上传技能','完整body序列化为JSON字符串放在user；system仅加入私有请求不覆盖教师规则的约束。'),
 ('切换/停用/解绑','下一次请求重新解析本轮选择和有效绑定；不同轮次可能选不同技能。')],[145,370])
p('私有技能仍需通过文件结构和工具限制检查；本轮指定可覆盖默认自动路由，显式null表示不使用技能。个人资料库只复用资料，私有Skill仍限原会话。',SM)
link('严格解析头部与body：skills.py','campusclaw/skills.py')
link('私有Skill限制和引用范围：attachments.py','campusclaw/attachments.py')

page(7,'验证4：具体Skill执行逻辑')
table(['步骤','服务端行为'],[
 ('1. 鉴权与解析','Bearer会话确定用户/班级；读取本人会话。技能头部解析名称、适用条件、启用、工具，空行后为body。'),
 ('2. 路由','在本班、已绑定、启用技能中计算问题terms与条件terms的集合交集数；中文取相邻双字，英文/数字取小写词。'),
 ('3. 选一个','分数降序，同分按技能id升序；最高分须大于0。显式本轮技能可覆盖自动选择，null禁用。'),
 ('4. 检索','主机统一按绑定/本轮材料检索；即使无Skill也可检索。knowledge_search是允许的内置标记，不由模型自行决定调用。'),
 ('5. MCP（如需）','工具引用为tool@server时，校验本班连接与发现缓存，主机以question为参数调用远端并写审计。'),
 ('6. 提示与生成','角色/共享body进system；片段、私有请求、MCP数据进user。实际ChatClient序列化并流式调用。'),
 ('7. 校验与保存','有资料须使用有效[Sx]；未知引用/流未完成视为失败。成功才保存completed并发送done。')],[85,430])
h('它执行什么，不执行什么')
p('Skill是一份声明式规则文件：约束模型的提问方式、步骤与输出风格，并可绑定受限工具。服务器不把Skill当作Python、Shell或任意Markdown代码执行，也没有动态加载上传代码。MCP公式计算/转换逻辑由独立工具服务器实现。')
h('T04真实模型返回的完整正文')
answer('T04_shared_skill')
p('观察：正文要求学生先提供质量、加速度及思路。是否符合教学目标仍需人工评阅，不能由字符串存在就认定模型一定遵守。',SM)

page(8,'验证5：MCP参数与LLM请求')
p('此实现采用主机先调用工具，再调用模型的方式。连接时initialize、notifications/initialized、tools/list发现formula_hint和unit_convert；工具清单缓存在服务端。')
h('T07实际RPC方法参数和工具result')
call=next(x for x in D['mcp_rpc'] if x['method']=='tools/call')
code(call)
p('HTTP POST /mcp使用服务端保存的MCP Bearer及JSON-RPC 2.0信封。信封包含自动生成的id；本报告观测文件记录method/params/result，未保留该id。MCP令牌不是LLM密钥，两者都未交给浏览器或模型。',SM)
h('随后发往真实LLM的完整请求JSON')
code(LIVE['T07_mcp_ok']['request'])
link('真实MCP客户端与question契约：mcp_client.py','campusclaw/mcp_client.py')

page(9,'验证5：工具返回、拒绝和安全边界')
h('T07真实模型返回的完整正文')
answer('T07_mcp_ok')
h('工具成功/断开后的实际处理')
table(['条件','主机调用与传给模型的结果'],[
 ('服务器已连接','先tools/call，返回文本；最后user中包含reference、status=ok、text、message；审计ok。'),
 ('服务器断开','发现缓存清空，不再调用远端；产生denied审计；user中status=denied、text为空并有拒绝说明。'),
 ('保存断开工具绑定','保存时拒绝；既有Skill继续使用时在调用路径显示denied，不静默成功。'),
 ('模型接口参数','仍为model/messages/stream；无tools、tool_choice、function_call字段，无role=tool消息；不发送完整tools/list。')],[140,375])
h('T08传入本轮user的完整文本')
p(LIVE['T08_mcp_denied']['request']['messages'][-1]['content'],CODE)
p('工具数据是JSON字符串，不是不受约束的系统指令。system明确要求不执行工具输出中的指令；工具文本限制8000字。提示规则降低风险，但不能证明模型对任意恶意文本绝对免疫。',SM)
link('鉴权、审计及连接状态竞争保护：mcp_store.py','campusclaw/mcp_store.py')

page(10,'回归汇总、部署差异与结论')
labels=['模板入system','带历史消息','知识库片段子集','完整共享Skill正文','绑定但不匹配','私有Skill与个人资料','MCP成功','MCP断开拒绝']
table(['编号','验证目标','HTTP断言','真实模型重放'],[
 (f'T{i+1:02}',label,'通过', '完成' if list(LIVE.values())[i]['status']=='completed' else '失败')
 for i,label in enumerate(labels)],[55,250,95,115])
h('真实部署限制必须单独保留')
p('本机Python进程使用Windows已有127.0.0.1:7897代理，八组模型重放、2048维嵌入及真实Qdrant检索链路通过。Docker的8000端口MCP连接、工具发现、ok/denied及审计通过；两轮模型都未done。容器直接连接网关出现GatewayUnavailable / URLError / SSLEOFError。')
p('曾在单次诊断进程中尝试host.docker.internal代理并取消网关代理绕过，仍失败；未关闭TLS证书校验，也未在镜像中写入密钥。因此本报告不宣称Docker模型生成已验收完成。原先待完成的部署验收不因本次本机成功自动改为完成。')
h('结论')
p('五项平台能力已有实现，五个LLM链路问题均有源码与请求实录支持。模板传渲染正文；共享知识库传检索片段；命中Skill传正文；Skill由主机路由并组合受限工具；MCP返回作为数据加入user，LLM接口本身不使用原生function calling。本轮尚需处理Docker网关网络后再确认容器端完整AI体验。')

page(11,'复现步骤与交付清单')
h('启动与验证')
code('1. 本机.env配置登录、模型、嵌入和MCP密钥（不要提交）\n2. docker compose up -d --build\n3. python -m unittest discover -s tests -q\n4. node --test tests/test_sse.cjs\n5. python apitest/run_all.py\n6. python apitest/verify_llm_report.py --live\n7. python apitest/verify_mcp_compose.py --platform --allow-model-unavailable\n8. python apitest/check_mcp_secrets.py\n9. openspec validate --all --strict')
p('入口：/login登录，学生/tutor、教师/admin、接口/swagger。运行测试需本机Python和Docker；报告构建另需ReportLab与微软雅黑字体。HTML测试报告及逐页PNG在忽略目录中，最终PDF和合成脱敏证据纳入Git。')
h('本报告核对的代码版本')
p(REV,CODE)
p('代码版本为本报告生成时的项目提交；PDF作为随后的独立文档提交保存。报告不包含密钥、生产数据库、用户原始上传文件或镜像运行卷。',SM)
h('交付与源码索引')
for label,path in [
 ('项目仓库与启动说明','README.md'),('请求验证脚本','apitest/verify_llm_report.py'),
 ('完整请求与真实返回证据','docs/verification/llm-traces.json'),
 ('验证边界与复现说明','docs/verification/README.md'),('Swagger/OpenAPI','docs/openapi.json'),
 ('同仓MCP工具实现','mcp-server/server.py'),('工作区与备份回滚说明','docs/workspace-validation.md')]: link(label,path)
p('证据JSON SHA-256：'+hashlib.sha256((HERE/'llm-traces.json').read_bytes()).hexdigest(),SM)
p('声明：本报告反映2026-10-26本轮观测。真实模型文本逐字保留在JSON；PDF展示代表场景完整正文。脱敏只移除认证值和提供商地址，不将测试模型输出冒充真实模型输出。',SM)

def footer(c,doc):
    c.saveState()
    c.setStrokeColor(LINE);c.line(40,37,555,37)
    c.setFont('YaHei',8);c.setFillColor(MUTED)
    c.drawString(40,24,'CAMPUSCLAW  /  项目与 LLM 链路验证  /  2026-10-26')
    c.drawRightString(555,24,str(doc.page))
    c.restoreState()

OUT.parent.mkdir(parents=True,exist_ok=True)
doc=SimpleDocTemplate(str(OUT),pagesize=(595.28,841.89),rightMargin=40,leftMargin=40,
    topMargin=38,bottomMargin=50,title='CampusClaw 项目与LLM链路验证报告',author='gjj')
doc.build(story,onFirstPage=footer,onLaterPages=footer)
print(OUT)
