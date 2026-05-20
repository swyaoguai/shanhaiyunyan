"""Prompt construction helpers for the novel cover generator."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping


FIXED_NEGATIVE_PROMPT = (
    "不要生成真实出版社、平台 Logo、水印、二维码；"
    "不要出现错别字、乱码文字、多余署名；"
    "避免低清晰度、过度模糊、脸部崩坏、手部畸形。"
)


@dataclass(frozen=True)
class CoverTemplate:
    id: str
    name: str
    genre: str
    description: str
    preview: str
    preview_image: str
    typography_prompt: str
    element_prompt: str
    variables: List[str]
    defaults: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "genre": self.genre,
            "description": self.description,
            "preview": self.preview,
            "preview_image": self.preview_image,
            "typography_prompt": self.typography_prompt,
            "element_prompt": self.element_prompt,
            "variables": list(self.variables),
            "defaults": dict(self.defaults),
        }


def _cover_template(
    *,
    template_id: str,
    name: str,
    genre: str,
    description: str,
    preview: str,
    preview_image: str,
    typography_style: str,
    defaults: Dict[str, str],
) -> CoverTemplate:
    return CoverTemplate(
        id=template_id,
        name=name,
        genre=genre,
        description=description,
        preview=preview,
        preview_image=preview_image,
        typography_prompt=(
            "文字：“{title}”，小字：“{author}·著”，文字在画面下方三分之一处，标题区域稳定可读，"
            f"{typography_style}"
        ),
        element_prompt=(
            "{characters}，{scene_background}，{symbols_props}，{atmosphere_color}，"
            "商业小说封面构图，主体清晰，背景服务于题材氛围，二维精修插画质感，高清细节。"
        ),
        variables=["characters", "scene_background", "symbols_props", "atmosphere_color"],
        defaults=defaults,
    )


COVER_TEMPLATES: List[CoverTemplate] = [
    _cover_template(
        template_id="wuxia_gold_blade",
        name="古风武侠金锋字",
        genre="武侠 / 仙侠 / 玄幻",
        description="剑刃飞白和金属高光适合大气磅礴的男频封面。",
        preview="金色剑锋书法字、墨色山河、仙侠气势",
        preview_image="/static/cover-examples/typography-01.jpg",
        typography_style=(
            "古风武侠艺术字，书法笔触飘逸凌厉，笔画带剑刃般的锋芒与飞白效果，"
            "金色渐变金属质感，边缘带亮白色高光与深灰色描边，外附柔和的白色辉光/光晕，"
            "字体带有仙侠玄幻的磅礴气势，适合小说封面，超清细节，8K，高对比度"
        ),
        defaults={
            "characters": "身负长剑的侠客主角，衣袂被山风掀起，背影坚毅",
            "scene_background": "云雾山河、古道与远处巍峨群峰",
            "symbols_props": "剑刃、山河纹样、飞白光痕",
            "atmosphere_color": "金色高光与墨色高反差，苍茫磅礴",
        },
    ),
    _cover_template(
        template_id="luxury_gilded",
        name="轻奢鎏金浮雕字",
        genre="现言 / 商战 / 豪门",
        description="烫金浮雕和干净背景适合高级商业感、豪门和契约题材。",
        preview="鎏金浮雕字、铂金描边、柔和高级光影",
        preview_image="/static/cover-examples/typography-02.jpg",
        typography_style=(
            "高级轻奢鎏金艺术字体，金属烫金质感，细腻铂金描边，立体浮雕字体，"
            "简约高级干净背景，光影柔和，高级商业艺术字体，高清质感，精致细腻"
        ),
        defaults={
            "characters": "气质冷静的都市男女主，轮廓利落，带高级商业杂志感",
            "scene_background": "极简深色空间、丝绒或大理石质感背景",
            "symbols_props": "合同、玫瑰、金色徽记或高定珠宝",
            "atmosphere_color": "柔和金色光影，干净克制，轻奢高级",
        },
    ),
    _cover_template(
        template_id="gothic_blood",
        name="恐怖哥特血滴字",
        genre="恐怖 / 惊悚 / 暗黑",
        description="尖锐红黑血滴字效适合强冲击力惊悚封面。",
        preview="暗红血滴、哥特尖角、白色外发光",
        preview_image="/static/cover-examples/typography-03.jpg",
        typography_style=(
            "恐怖哥特风格字体，尖锐棱角字体，红色血滴效果，液态血迹滴落纹理，"
            "暗黑惊悚艺术字，暗红色渐变，白色外发光描边，金属锐利质感，"
            "毛骨悚然的血腥文字，暗黑小说封面标题，高对比度，强烈冲击力，超高清，细节拉满"
        ),
        defaults={
            "characters": "被阴影笼罩的调查者或惊恐主角，半张脸隐入黑暗",
            "scene_background": "废弃宅院、雨夜街巷或红雾森林",
            "symbols_props": "血色信封、旧钥匙、裂纹镜面",
            "atmosphere_color": "暗红与黑色强对比，惊悚压迫",
        },
    ),
    _cover_template(
        template_id="chinese_horror_brush",
        name="中式惊悚血墨字",
        genre="中式恐怖 / 悬疑 / 民俗",
        description="竖版血墨毛笔字适合民俗怪谈和中式恐怖网文。",
        preview="竖排血墨字、枯笔飞白、旧宅阴影",
        preview_image="/static/cover-examples/typography-04.jpg",
        typography_style=(
            "暗黑惊悚毛笔书法字体，凌厉锋利笔触，暗红血色水墨质感，猩红血迹喷溅效果，"
            "破损斑驳做旧纹理，暗黑哥特悬疑氛围，红白强对比光影，白色锐利外发光描边，"
            "竖版排版，中式恐怖网文标题，高对比度氛围感，高清细节，阴森诡异氛围感，"
            "血色晕染边缘，枯笔飞白笔触"
        ),
        defaults={
            "characters": "夜行的主角背影，手持旧灯笼，身后隐约有影",
            "scene_background": "破旧祠堂、深巷门楼或荒村老宅",
            "symbols_props": "红纸符、铜铃、旧灯笼、斑驳木门",
            "atmosphere_color": "暗红血墨与冷白光对撞，阴森诡异",
        },
    ),
    _cover_template(
        template_id="sweet_campus_bluegreen",
        name="甜宠蓝绿花体字",
        genre="青春 / 校园 / 甜宠",
        description="清新蓝绿色手写花体适合校园恋爱和治愈甜文。",
        preview="蓝绿渐变花体、星光光斑、柔焦校园",
        preview_image="/static/cover-examples/typography-05.jpg",
        typography_style=(
            "甜宠言情小说封面艺术字体，梦幻渐变蓝绿色调，圆润流畅的手写花体字，"
            "带有飘逸装饰性曲线，高光与外发光效果，清新柔焦质感，点缀星光与光斑元素，"
            "治愈系青春氛围感，字体边缘有柔和光晕，干净通透的色彩，细腻的光泽描边，"
            "清新校园恋爱风格，高清细节"
        ),
        defaults={
            "characters": "青春感男女主并肩走在阳光里，表情自然温柔",
            "scene_background": "校园林荫道、教室窗边或夏日操场",
            "symbols_props": "星光、光斑、课本、心动便签",
            "atmosphere_color": "蓝绿色梦幻渐变，柔焦清新，治愈明亮",
        },
    ),
    _cover_template(
        template_id="fresh_xianxia_jade",
        name="清新古风青玉字",
        genre="古风 / 仙侠 / 治愈",
        description="青绿色玉石通透感适合清新仙侠和草木灵气题材。",
        preview="青绿玉石花体、菱形星光、仙侠治愈",
        preview_image="/static/cover-examples/typography-06.jpg",
        typography_style=(
            "清新古风花体艺术字，青绿色渐变光泽字体，带有飘逸装饰性卷曲线条，"
            "金属玉石般通透质感，柔和外发光描边，点缀星光与菱形装饰元素，"
            "原神草系风格，梦幻治愈氛围感，细腻高光描边，手写毛笔风曲线，"
            "仙侠网文封面字体，高通透度，青绿色调渐变，边缘柔化光晕，超高清细节"
        ),
        defaults={
            "characters": "灵气充盈的少年或少女主角，衣袂轻盈，手中有草木灵光",
            "scene_background": "竹林、云海仙境、发光藤蔓与清泉",
            "symbols_props": "青玉、草叶灵纹、星光菱形装饰",
            "atmosphere_color": "青绿色通透光泽，梦幻治愈，空气清澈",
        },
    ),
    _cover_template(
        template_id="cute_chibi_bold",
        name="Q版软萌粗描边字",
        genre="团宠 / 萌宝 / 轻喜",
        description="白底黑边胖乎乎字形适合可爱、轻松和合家欢题材。",
        preview="Q版圆润字、黑白粗描边、星星涂鸦",
        preview_image="/static/cover-examples/typography-07.jpg",
        typography_style=(
            "Q版可爱圆润艺术字体，卡通漫画风加粗字体，白色填充+黑色粗描边，"
            "圆润饱满的胖乎乎笔画，搭配星星、圆点、小三角等可爱装饰元素，"
            "带有俏皮活泼的手绘涂鸦感，白底黑边醒目清晰，网文小说封面标题，"
            "高对比度，可爱软萌风格，细节干净利落"
        ),
        defaults={
            "characters": "Q版小主角或萌系家庭角色，表情活泼讨喜",
            "scene_background": "暖色玩具屋、糖果街道或轻喜剧生活场景",
            "symbols_props": "星星、圆点、小三角、贴纸涂鸦",
            "atmosphere_color": "明亮高对比，软萌活泼，干净利落",
        },
    ),
    _cover_template(
        template_id="wuxia_blue_lightning",
        name="青蓝武侠电光字",
        genre="武侠 / 游戏风 / 仙侠",
        description="青蓝金属和火焰电光适合战斗感更强的武侠封面。",
        preview="青蓝金属书法、电光火焰、武器装饰",
        preview_image="/static/cover-examples/typography-08.jpg",
        typography_style=(
            "古风武侠游戏标题字体，凌厉锋利的毛笔书法字，青蓝色金属光泽渐变，"
            "带有发光外描边，水墨笔触质感，字体边缘带有火焰/电光特效，"
            "带有金属反光和光晕，暗黑古风背景，高对比度，大气磅礴的仙侠/武侠风格，"
            "带有武器装饰元素，超高清细节，强烈视觉冲击力"
        ),
        defaults={
            "characters": "拔剑出鞘的武者主角，动作凌厉，斗篷翻飞",
            "scene_background": "雷雨山巅、古战场或暗黑仙门",
            "symbols_props": "长剑、枪戟、青蓝电光、火焰边缘",
            "atmosphere_color": "冷青蓝金属光与暗色背景强对比",
        },
    ),
    _cover_template(
        template_id="romance_blue_pink",
        name="现言甜宠蓝粉花体字",
        genre="现言 / 甜宠 / 霸总",
        description="蓝紫玫红花体适合少女心、现代甜宠和都市恋爱。",
        preview="蓝紫玫红渐变、爱心星光、华丽曲线",
        preview_image="/static/cover-examples/typography-09.jpg",
        typography_style=(
            "甜宠言情小说封面艺术字，浪漫优雅花体手写字体，蓝紫到玫红渐变色彩，"
            "细腻高光描边，带有飘逸卷曲装饰线条，柔和外发光效果，点缀星光、爱心小装饰，"
            "少女心爆棚的氛围感，字体边缘柔化光晕，通透干净的色彩质感，"
            "适配现言甜宠/霸总网文，高清细节，精致华丽的曲线设计"
        ),
        defaults={
            "characters": "现代都市男女主靠近对视，气氛暧昧但克制",
            "scene_background": "夜色城市、玻璃窗、玫瑰与柔光",
            "symbols_props": "爱心星光、玫瑰、戒指或高楼灯影",
            "atmosphere_color": "蓝紫到玫红渐变，通透干净，浪漫华丽",
        },
    ),
    _cover_template(
        template_id="ancient_romance_platinum",
        name="古言白金花瓣字",
        genre="古言 / 虐恋 / 仙侠言情",
        description="白金金属书法和红花瓣适合清冷深情的古言封面。",
        preview="白金毛笔字、红色花瓣、清冷深情",
        preview_image="/static/cover-examples/typography-10.jpg",
        typography_style=(
            "古风言情小说封面艺术字体，凌厉飘逸的毛笔书法字，白金色渐变金属光泽，"
            "带有深色外描边和红色高光点缀，边缘带柔化光晕，搭配飘落的红色花瓣装饰，"
            "水墨风笔触，苍劲有力的笔画，带有飞白效果，清冷又深情的氛围感，高对比度，"
            "适配古言虐恋/仙侠言情网文封面，超高清细节，精致的金属反光质感"
        ),
        defaults={
            "characters": "古装男女主远近错位，一人回望，一人背影渐远",
            "scene_background": "月下宫墙、雪夜长街或仙门台阶",
            "symbols_props": "红色花瓣、玉簪、信笺、薄雾",
            "atmosphere_color": "白金清冷光泽配深色描边，深情克制",
        },
    ),
    _cover_template(
        template_id="cyber_mecha_neon",
        name="赛博机甲霓虹字",
        genre="科幻 / 机甲 / 男频爽文",
        description="硬朗科技粗体和青蓝霓虹适合科幻机甲与未来战争。",
        preview="青蓝金属粗体、机甲切割线、霓虹描边",
        preview_image="/static/cover-examples/typography-11.jpg",
        typography_style=(
            "赛博朋克科幻机甲风字体，硬朗厚重的科技感粗体字，青蓝色金属渐变光泽，"
            "带有尖锐棱角与机甲切割线条，发光霓虹描边，金属镀铬质感，"
            "带有未来科技几何装饰（三角/机械纹路），高对比度，冷色调，"
            "适配科幻男频爽文/机甲网文封面，超高清细节，强烈视觉冲击力"
        ),
        defaults={
            "characters": "驾驶员或机甲战士主角，面部被冷光切出轮廓",
            "scene_background": "未来机库、星际战场或霓虹城市天际线",
            "symbols_props": "机甲装甲片、三角几何纹路、全息界面",
            "atmosphere_color": "青蓝冷光、高对比金属质感、未来科技感",
        },
    ),
    _cover_template(
        template_id="male_red_gold_seal",
        name="红金男频印章字",
        genre="三国 / 穿越 / 古风爽文",
        description="正红金属书法和印章框适合厚重豪迈的历史穿越题材。",
        preview="红金撞色、圆形印章、豪迈毛笔字",
        preview_image="/static/cover-examples/typography-12.jpg",
        typography_style=(
            "古风男频爽文小说封面艺术字，大气磅礴的毛笔书法字体，正红渐变金属光泽，"
            "带有鎏金高光与外发光描边，笔画苍劲飘逸、笔锋锐利有力，搭配圆形印章式文字框，"
            "点缀暖金色星光光斑，带有水墨飞白效果，红金撞色强烈对比，"
            "适配三国/穿越古风网文，高清细节，厚重豪迈的氛围感"
        ),
        defaults={
            "characters": "披甲主角立于战旗前，目光坚定，气势压场",
            "scene_background": "古战场、城楼烽火或王朝大殿",
            "symbols_props": "圆形印章、战旗、赤色鼎纹、金色光斑",
            "atmosphere_color": "红金强对比，厚重豪迈，热血昂扬",
        },
    ),
    _cover_template(
        template_id="female_purple_vertical",
        name="古言女频紫底白字",
        genre="古言 / 女频 / 宫廷",
        description="紫底白色竖排书法适合柔美大气的古言女频封面。",
        preview="纯白竖排书法、深紫背景、红色小印章",
        preview_image="/static/cover-examples/typography-13.jpg",
        typography_style=(
            "古言女频小说封面艺术字，温婉飘逸的古风毛笔书法字体，纯白色笔触，"
            "带有柔和飞白效果，线条纤细灵动，竖排排版，搭配红色边框竖排小字印章，"
            "适配深紫色古风背景，字体边缘干净利落，带有淡淡的朦胧质感，"
            "柔美又大气的古风言情风格，高清细节，笔触流畅自然"
        ),
        defaults={
            "characters": "古装女主立于帘幕后，神情温婉却有韧性",
            "scene_background": "深紫色宫苑、纱帘、花枝与夜雾",
            "symbols_props": "红色竖排小印章、花枝、玉佩、纱帘",
            "atmosphere_color": "深紫朦胧背景配纯白笔触，柔美大气",
        },
    ),
]


def get_cover_templates() -> List[Dict[str, Any]]:
    """Return public cover template definitions."""
    return [template.to_dict() for template in COVER_TEMPLATES]


def _template_by_id(template_id: str) -> CoverTemplate:
    wanted = str(template_id or "").strip()
    for template in COVER_TEMPLATES:
        if template.id == wanted:
            return template
    raise ValueError(f"未知封面模板：{template_id}")


def _compact_text(value: Any, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = _compact_text(value)
        if text:
            return text
    return ""


def _join_non_empty(values: Iterable[Any], *, limit: int = 420) -> str:
    parts: List[str] = []
    total = ""
    for value in values:
        text = _compact_text(value, limit)
        if not text:
            continue
        candidate = "；".join([*parts, text])
        if len(candidate) > limit:
            break
        parts.append(text)
        total = candidate
    return total


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _infer_visual_elements_from_seed(seed_text: str, title: str, template: CoverTemplate) -> Dict[str, str]:
    """Infer cover elements from user-provided names and ideas before template defaults."""
    text = _compact_text(seed_text, 900)
    title_text = _compact_text(title, 80)
    if not text and not title_text:
        return {}

    subject = _first_non_empty(text, title_text)
    inferred: Dict[str, str] = {}

    if _contains_any(subject, ("孙悟空", "悟空", "齐天大圣", "金箍棒", "赛亚人")):
        inferred.update(
            {
                "characters": _first_non_empty(
                    text,
                    "孙悟空式主角立于画面中央，桀骜、热血，衣甲与发丝被能量风掀起",
                ),
                "scene_background": "云海天宫、破碎石阶与远处翻涌的金色能量风暴，带神话冒险感",
                "symbols_props": "金箍棒、祥云纹、碎石、金色斗气光环",
                "atmosphere_color": "金橙能量光与深蓝夜色对比，热血、神性、史诗感",
            }
        )
    elif _contains_any(subject, ("赛博", "机甲", "星舰", "未来", "宇宙", "星际", "AI", "机器人")):
        inferred.update(
            {
                "characters": f"{subject}，冷光勾勒轮廓，姿态坚定，带未来战斗感",
                "scene_background": "霓虹城市、星舰残骸或未来机库，远处有冷色能量光",
                "symbols_props": "全息界面、机械纹路、三角科技符号、金属碎片",
                "atmosphere_color": "青蓝冷光、金属质感、高对比未来科技氛围",
            }
        )
    elif _contains_any(subject, ("恐怖", "惊悚", "诡异", "悬疑", "血", "鬼", "怪谈", "红月")):
        inferred.update(
            {
                "characters": f"{subject}，主角半身隐入阴影，表情克制紧张",
                "scene_background": "雨夜旧街、废弃宅院或红雾笼罩的城市角落",
                "symbols_props": "旧钥匙、裂纹镜面、红色信封、血色光痕",
                "atmosphere_color": "暗红与冷黑强对比，压迫、悬疑、惊悚",
            }
        )
    elif _contains_any(subject, ("校园", "甜宠", "恋爱", "青春", "治愈", "少女", "霸总", "豪门")):
        inferred.update(
            {
                "characters": f"{subject}，主角关系明确，表情自然，有心动瞬间",
                "scene_background": "校园林荫道、都市玻璃窗或暖光街角",
                "symbols_props": "星光、便签、玫瑰、爱心光斑",
                "atmosphere_color": "柔焦暖光，清新通透，浪漫治愈",
            }
        )
    elif _contains_any(subject, ("宫廷", "古言", "王朝", "穿越", "三国", "将军", "女帝", "公主")):
        inferred.update(
            {
                "characters": f"{subject}，古装主角站姿稳定，服饰层次清晰",
                "scene_background": "宫墙、长街、城楼或王朝大殿，远景有旗影与薄雾",
                "symbols_props": "玉佩、花瓣、印章、战旗或信笺",
                "atmosphere_color": "红金或白金高光，厚重古风，情绪克制",
            }
        )
    elif _contains_any(subject, ("修仙", "仙侠", "玄幻", "灵气", "剑", "宗门", "神魔", "妖")):
        inferred.update(
            {
                "characters": f"{subject}，主角持剑或凝聚灵光，衣袂翻飞",
                "scene_background": "云海仙山、宗门石阶、古战场或秘境入口",
                "symbols_props": "长剑、符纹、灵光、山河纹样",
                "atmosphere_color": "高幻想光效，金色或青蓝灵光，磅礴有层次",
            }
        )
    else:
        inferred.update(
            {
                "characters": f"{subject}，主角形象明确，姿态有故事张力",
                "scene_background": f"围绕“{title_text or template.genre}”建立封面场景，背景与角色命运相关",
                "symbols_props": "与书名和主角相关的核心符号、光痕和装饰纹样",
                "atmosphere_color": f"贴合{template.genre}题材的商业封面色彩，主体突出，氛围清晰",
            }
        )
    return {key: _compact_text(value, 260) for key, value in inferred.items() if _compact_text(value)}


def _iter_dict_rows(rows: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(rows, dict):
        candidate = rows.get("items") or rows.get("chapters") or rows.get("data") or []
    else:
        candidate = rows
    if not isinstance(candidate, list):
        return []
    return [row for row in candidate if isinstance(row, Mapping)]


def _format_named_rows(rows: Any, *, limit: int = 3) -> str:
    parts: List[str] = []
    for row in list(_iter_dict_rows(rows))[:limit]:
        name = _first_non_empty(row.get("name"), row.get("title"), row.get("chapter_title"))
        role = _first_non_empty(row.get("role"), row.get("type"))
        desc = _first_non_empty(
            row.get("appearance"),
            row.get("description"),
            row.get("summary"),
            row.get("content"),
            row.get("details"),
        )
        if name and role and desc:
            parts.append(f"{name}（{role}）：{desc}")
        elif name and desc:
            parts.append(f"{name}：{desc}")
        elif name:
            parts.append(name)
        elif desc:
            parts.append(desc)
    return "；".join(parts)


def _query_terms(query: str) -> List[str]:
    text = _compact_text(query, 160)
    if not text:
        return []
    terms = [item.strip() for item in re.split(r"[\s,，、;；/|]+", text) if item.strip()]
    if text not in terms:
        terms.insert(0, text)
    return terms[:8]


class ProjectCoverContextExtractor:
    """Extract cover-friendly elements from the current project."""

    def extract(self, project_manager: Any) -> Dict[str, str]:
        project = project_manager.get_current_project() if project_manager else None
        project_name = _first_non_empty(getattr(project, "name", ""))
        description = _first_non_empty(getattr(project, "description", ""))
        genre = _first_non_empty(getattr(project, "novel_type", ""))

        characters = _format_named_rows(project_manager.load_project_data("characters"), limit=3)
        worldbuilding = _format_named_rows(project_manager.load_project_data("worldbuilding"), limit=4)
        items = _format_named_rows(project_manager.load_project_data("items"), limit=4)
        outline = _format_named_rows(project_manager.load_project_data("outline"), limit=3)
        chapters = _format_named_rows(project_manager.load_project_data("chapters"), limit=2)
        scene_background = _join_non_empty([worldbuilding, outline, chapters, description], limit=520)

        return {
            "title": project_name,
            "genre": genre,
            "summary": description,
            "characters": characters,
            "scene_background": scene_background,
            "symbols_props": items,
            "atmosphere_color": _infer_atmosphere(genre, description, worldbuilding),
        }

    def find_character_context(self, project_manager: Any, query: str) -> str:
        terms = _query_terms(query)
        if not terms or not project_manager:
            return ""
        rows = list(_iter_dict_rows(project_manager.load_project_data("characters")))
        matched: List[Mapping[str, Any]] = []
        for row in rows:
            haystack = " ".join(
                _compact_text(row.get(key), 260)
                for key in ("name", "title", "role", "appearance", "description", "summary", "content", "details")
                if _compact_text(row.get(key))
            )
            if any(term and term in haystack for term in terms):
                matched.append(row)
        return _format_named_rows(matched, limit=2)


def _infer_atmosphere(genre: str, description: str, worldbuilding: str) -> str:
    text = f"{genre} {description} {worldbuilding}"
    if any(keyword in text for keyword in ("恐怖", "诡异", "悬疑", "惊悚", "异常", "红月")):
        return "暗色基调，红黑对比，压抑氛围与强光效明暗对比"
    if any(keyword in text for keyword in ("科幻", "星舰", "未来", "机甲", "赛博")):
        return "冷色科技光效，远景宏大，金属质感清晰"
    if any(keyword in text for keyword in ("言情", "治愈", "甜宠", "校园")):
        return "柔和暖光，情绪细腻，画面干净通透"
    if any(keyword in text for keyword in ("玄幻", "修仙", "仙侠", "奇幻")):
        return "高幻想色彩，灵光流动，层次丰富"
    if any(keyword in text for keyword in ("三国", "历史", "穿越", "王朝")):
        return "厚重红金色调，史诗感强，光影豪迈"
    return ""


class CoverPromptBuilder:
    """Build typography, element and final prompts for cover generation."""

    def __init__(self, extractor: ProjectCoverContextExtractor | None = None):
        self.extractor = extractor or ProjectCoverContextExtractor()

    def build_prompt(
        self,
        *,
        project_manager: Any,
        template_id: str,
        source_mode: str = "project_plus_custom",
        title: str = "",
        author: str = "",
        custom_elements: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        template = _template_by_id(template_id)
        custom = {
            str(key): _compact_text(value, 360)
            for key, value in dict(custom_elements or {}).items()
            if _compact_text(value)
        }
        creative_idea = _compact_text(custom.get("creative_idea"), 520)
        project_elements = self.extractor.extract(project_manager)
        source_mode = str(source_mode or "project_plus_custom").strip() or "project_plus_custom"

        if source_mode == "custom":
            merged: Dict[str, str] = {}
        else:
            merged = dict(project_elements)

        if source_mode in {"custom", "project_plus_custom"}:
            merged.update(custom)

        character_query = _compact_text(custom.get("characters"))
        if character_query and source_mode != "custom":
            matched_character = self.extractor.find_character_context(project_manager, character_query)
            if matched_character:
                merged["characters"] = _join_non_empty([character_query, matched_character], limit=420)

        variable_keys = [
            "characters",
            "scene_background",
            "symbols_props",
            "atmosphere_color",
        ]
        project_context_empty = not any(_compact_text(project_elements.get(key)) for key in variable_keys)
        custom_elements_empty = not any(_compact_text(custom.get(key)) for key in variable_keys)
        source_content_empty = not any(_compact_text(merged.get(key)) for key in variable_keys)
        idea_only_source = source_content_empty and bool(creative_idea)

        project_title = project_elements.get("title", "")
        explicit_title = _compact_text(title)
        merged["title"] = _first_non_empty(explicit_title, project_title, template.defaults.get("title"), "未命名小说")
        merged["author"] = _first_non_empty(author, merged.get("author"), "XXXX")

        seed_text = _join_non_empty(
            [
                creative_idea,
                merged.get("characters"),
                merged.get("scene_background"),
                merged.get("symbols_props"),
                project_elements.get("genre"),
                project_elements.get("summary"),
                merged.get("title"),
            ],
            limit=900,
        )
        inferred_elements = _infer_visual_elements_from_seed(seed_text, merged["title"], template)
        inferred_fields: List[str] = []
        for key in variable_keys:
            if not _compact_text(merged.get(key)) and _compact_text(inferred_elements.get(key)):
                merged[key] = inferred_elements[key]
                inferred_fields.append(key)

        fallback_fields: List[str] = []
        for key, value in template.defaults.items():
            before_default = merged.get(key)
            merged[key] = _first_non_empty(before_default, value)
            if key in variable_keys and not _compact_text(before_default) and _compact_text(merged.get(key)):
                fallback_fields.append(key)

        typography_prompt = template.typography_prompt.format(**merged)
        element_prompt = template.element_prompt.format(**merged)
        final_prompt = "\n".join(
            [
                typography_prompt,
                element_prompt,
                "构图要求：小说商业封面，主体清晰，远看可识别，标题区域稳定可读，避免真实平台标识。",
                f"禁止项：{FIXED_NEGATIVE_PROMPT}",
            ]
        )

        title_source = "custom" if explicit_title else ("project" if project_title else "fallback")
        title_warning = ""
        if title_source == "project":
            title_warning = f"当前书名默认使用项目名“{project_title}”。如果项目名不是小说书名，请改成正确书名后再生成。"

        completion_notice = ""
        prompt_generation_mode = "project_or_custom"
        if inferred_fields:
            completion_notice = (
                "已根据书名、角色名或你的创作想法补全缺失画面元素；字体提示词保持所选示例不变。"
            )
            prompt_generation_mode = "idea_inferred" if idea_only_source else "local_inferred"
        if source_content_empty and not inferred_fields:
            completion_notice = (
                "当前选择的元素来源没有可用封面内容，已按所选字体模板补全角色、场景、道具和色彩；"
                "如果项目为空，建议填写四个元素或“创作想法”。"
            )
            prompt_generation_mode = "template_defaults"

        return {
            "template_id": template.id,
            "template_name": template.name,
            "title": merged["title"],
            "title_source": title_source,
            "title_warning": title_warning,
            "author": merged["author"],
            "source_mode": source_mode,
            "elements": {
                key: merged.get(key, "")
                for key in [
                    "characters",
                    "scene_background",
                    "symbols_props",
                    "atmosphere_color",
                ]
            },
            "custom_elements": custom,
            "creative_idea": creative_idea,
            "inferred_fields": inferred_fields,
            "fallback_fields": fallback_fields,
            "project_context_empty": project_context_empty,
            "custom_elements_empty": custom_elements_empty,
            "completion_notice": completion_notice,
            "prompt_generation_mode": prompt_generation_mode,
            "prompt_api_config_id": "",
            "prompt_model": "",
            "typography_prompt": typography_prompt,
            "element_prompt": element_prompt,
            "final_prompt": final_prompt,
            "negative_prompt": FIXED_NEGATIVE_PROMPT,
        }

    def apply_elements(
        self,
        draft: Mapping[str, Any],
        elements: Mapping[str, Any],
        *,
        prompt_generation_mode: str,
        prompt_api_config_id: str = "",
        prompt_model: str = "",
        completion_notice: str = "",
        prompt_model_warning: str = "",
    ) -> Dict[str, Any]:
        """Return a prompt draft rebuilt with enhanced visual elements."""
        template = _template_by_id(str(draft.get("template_id") or ""))
        existing_elements = draft.get("elements") if isinstance(draft.get("elements"), Mapping) else {}
        merged: Dict[str, str] = {
            "title": _first_non_empty(draft.get("title"), "未命名小说"),
            "author": _first_non_empty(draft.get("author"), "XXXX"),
        }

        for key in template.variables:
            merged[key] = _first_non_empty(
                elements.get(key),
                existing_elements.get(key),
                template.defaults.get(key),
            )

        typography_prompt = _first_non_empty(draft.get("typography_prompt")) or template.typography_prompt.format(**merged)
        element_prompt = template.element_prompt.format(**merged)
        final_prompt = "\n".join(
            [
                typography_prompt,
                element_prompt,
                "构图要求：小说商业封面，主体清晰，远看可识别，标题区域稳定可读，避免真实平台标识。",
                f"禁止项：{FIXED_NEGATIVE_PROMPT}",
            ]
        )

        result = dict(draft)
        result.update(
            {
                "elements": {key: merged.get(key, "") for key in template.variables},
                "typography_prompt": typography_prompt,
                "element_prompt": element_prompt,
                "final_prompt": final_prompt,
                "prompt_generation_mode": prompt_generation_mode,
                "prompt_api_config_id": prompt_api_config_id,
                "prompt_model": prompt_model,
            }
        )
        if completion_notice:
            result["completion_notice"] = completion_notice
        if prompt_model_warning:
            result["prompt_model_warning"] = prompt_model_warning
        return result
