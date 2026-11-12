# 文件路径: views/help_ui.py
# 使用说明独立页：分卡片展示快速上手、模板与编号、董监高流程、自定义网站与小提示。

import customtkinter as ctk

from views import theme


class HelpFrame(ctk.CTkFrame):
    """静态说明页：内容见 _SECTIONS，修改文案直接编辑该常量即可。"""

    _SECTIONS = [
        ("📷 诚信核查截图（主流程）", [
            "1. 输入待核查对象：名称 证件号（证件号可空），回车或点「添加」",
            "2. 在「核查范围」选择方案（债券模板 / 董监高模板）并勾选网站",
            "3. 点「开始核查」——进度条滚动期间请勿最小化浏览器或锁屏（物理截图约束），务必在前台运行，不能有遮挡",
            "4. 跑完自动核验：对象行徽章 ✅成功 ❌失败；点「⚠ 仅选上次失败」再跑即补缺图",
            "· 每轮结果单独存放：output/run_时间戳/subj_001…，目录名不含主体名称（对外演示安全）",
            "5. 运行期间如果浏览器出现弹窗，网页未能成功加载，或出现其他异常，请先手动处理后再继续，可以在运行期间直接鼠标操作。",
            "   鼠标操作会影响截图结果，手动操作后请重新运行（一般仅会在首次运行时出现，后续可直接补缺图）",
        ]),
        ("💾 模板与编号", [
            "· 「待核查对象」右上角「💾 存为模板」保存当前名单；「核查模板」页可管理/载入",
            "· 模板名单行格式：[编号] 名称 [证件号]，编号形如 1-3-1-3-1",
            "· 「核查说明生成」页填编号映射 → docx 文件名加「编号 」前缀；无编号走原名",
            "· 所有 docx 一律输出到统一输出目录，不会写入任何公司文件夹",
        ]),
        ("👔 董监高核查", [
            "· 左侧「董监高核查」页三步：切换模板截图 → 截图整理（每人一夹→每站一夹）",
            "· 生成汇总文档：《项目组关于董监高人员诚信信息的核查说明》，首页空白供手写说明",
            "· 站点标题行默认插入，可关闭变为纯图片流",
        ]),
        ("🌐 自定义网站", [
            "· 「核查范围」底部输入 URL 添加自定义站点",
            "· 同名添加可临时替换内置站点；删除该自定义项即自动恢复内置原版",
            "· 删除前会弹确认框并显示 URL，误删可按 URL 重新添加",
            "示例1：搜索页的网站为【http://www.zghaq.gov.cn/search/index.html?q=xx】",
            "自定义网站则为【http://www.zghaq.gov.cn/search/index.html?q=】，即去掉搜索关键字部分，程序会自动在后面拼接待核查对象名称",
            "示例2：搜索页的网站为【https://www.caidian.gov.cn/SITE/whs_70/search.html?searchWord=xx&siteId=17&pageSize=10&orderBy=all】",
            "自定义网站则为【https://www.caidian.gov.cn/SITE/whs_70/search.html?searchWord={company}&siteId=17&pageSize=10&orderBy=all】",
            "即将搜索关键字部分替换为 {company}，程序会自动在后面拼接待核查对象名称",
        ]),
        ("💡 小提示", [
            "· 同一时刻只能运行一个核查任务；文书网站需在前台配合登录",
            "· 「清除记录」仅删除核验状态文件，不影响任何已截图",
            "· 深/浅色主题在侧边栏底部切换；「清除日志」只清屏不删文件",
        ]),
    ]

    def __init__(self, master, **kwargs):
        super().__init__(master, corner_radius=0, fg_color="transparent", **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)

        header = ctk.CTkLabel(
            scroll, text="诚信核查自动化截图 · 使用说明", font=theme.f(17, bold=True), anchor="w",
        )
        header.pack(fill="x", pady=(0, 12))

        for title, lines in self._SECTIONS:
            card, body, _ = theme.make_card(scroll, title=title)
            card.pack(fill="x", pady=(0, 12))
            for line in lines:
                ctk.CTkLabel(
                    body, text=line, font=theme.f(12),
                    justify="left", anchor="w",
                ).pack(fill="x", pady=1)
