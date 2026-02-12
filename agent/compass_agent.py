from pydantic import BaseModel, Field

from agent.base import BaseAgent
from core import settings
from core.compass import CompassSelection, list_compass_choice_cards


class CompassChoicesAgent(BaseAgent):

    def __init__(self):
        super().__init__(
            settings.L0_AGENT_MODEL,
            "You are a routing agent. Given user content and available Compass choices, select the best CompassSelection. Output ONLY valid JSON.",
        )

    class _CompassSelectionResponse(BaseModel):
        director: str | None = Field(default=None)
        style: list[str] | None = Field(default=None)
        rationale: str = Field(default="")

    async def infer_compass(
        self,
        *,
        content: str,
        root_dir: str = "./compass",
    ) -> CompassSelection:
        director_cards = list_compass_choice_cards(axis="director", root_dir=root_dir)
        style_cards = list_compass_choice_cards(axis="style", root_dir=root_dir)
        cards = {
            "director": director_cards,
            "style": style_cards,
        }

        msg = (
            "You are given a user's content for video/script generation. "
            "Choose the most suitable CompassSelection from the available choices.\n\n"
            "Rules:\n"
            "- You MUST choose from the provided choices only.\n"
            "- If none applies, set the field to null.\n"
            "- director should be selected when the content clearly implies a directing/structuring preference.\n"
            "- style can be a list; keep it short (0-3 items).\n"
            "- rationale should be short.\n\n"
            f"AVAILABLE_COMPASS_CARDS: {cards}\n\n"
            f"USER_CONTENT:\n{content}"
        )

        resp = await self.infer(
            message=msg,
            response_model=self._CompassSelectionResponse,
            need_thinking=False,
        )

        return CompassSelection(
            director=resp.director,
            style=resp.style,
        )

if __name__ == '__main__':
    content = """
            公益视频

            片名（暂定）：
            《再忙一下？》

            📌 核心主题

            别把“再忙一下”变成永远的借口。
            关注亲情、精神健康、现实陪伴，而不是数字世界里的虚拟成就。

        0–3s | 开场

    黑屏字幕音：
    📱 “再忙一下…”

    镜头：
    手指点击手机屏幕，震动提示音。

    3–8s | 平行剪辑，多线叙事

    画面 A：
    年轻人加班到深夜，桌上外卖盒、邮件推送不断闪烁。

    画面 B：
    父亲坐在沙发上等女儿回家，目光停在门口。

    画面 C：
    母亲正在老照片前微笑，却又叹气。

    音轨：
    耳边不断重复——
    📱 “再忙一下…”（声音越来越快）

    8–15s | 情绪冲突

    画面快切：

    电话未接

    未回的家庭群消息

    儿童生日蜡烛慢慢燃尽

    父亲独自吃饭

    母亲握着手机落泪

    一句旁白缓缓出现：
    📢 “忙，不一定是成长；逃避，也正叫忙。”

    15–22s | 触动反转

    画面切换：
    手机静止在桌上，年轻人抬头看向父母。

    慢镜头：
    父母微笑、孩子跑向他，一瞬间穿透心灵。

    旁白（轻柔但坚定）：
    📢 “陪伴，不是时间碎片，是把握现在。”

    22–30s | 结尾标语 & 呼吁

    黑底白字：

    💬 再忙一下，就可能错过一生的温暖。

    公益标语（缓显）：

    ✨ 陪，是最不忙的善意.
    📌 关爱亲情 • 珍惜当下

    包括 Logo + 机构名称 + 简短口号。

    （背景音乐在此处渐弱收尾）

    """
    agents= CompassChoicesAgent()
