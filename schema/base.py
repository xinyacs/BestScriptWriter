from typing import Any, List, Literal, Optional
from pydantic import BaseModel, Field, conint


class ScriptSection(BaseModel):
    item_id: Optional[str] = None
    section: str = Field(..., description="该段落的脚本文案/分镜描述")
    rationale: str = Field(..., description="该段落的导演/算法侧设计理由")
    duration: int = Field(
        ...,
        ge=1,
        description="该段落时长（秒），必须 >= 1"
    )
    
    def __str__(self):
        return f"[{self.duration}s] {self.section}\n理由: {self.rationale}"


class L1VideoScript(BaseModel):
    title: str
    total_duration: int = Field(
        ...,
        ge=1,
        description="总时长（秒）"
    )
    keywords: List[str] = Field(default_factory=list)
    body: List[ScriptSection] = Field(default_factory=list)
    need_write_next: bool = False
    notes: str = ""

    def assert_total_duration(self) -> None:
        total = sum(x.duration for x in self.body)
        if total != self.total_duration:
            raise ValueError(
                f"total_duration={self.total_duration} "
                f"但 body.duration 总和={total}"
            )

    def __str__(self):
        sections = []
        for i, section in enumerate(self.body, 1):
            sections.append(
                f"{i}. [{section.duration}s] {section.section}\n"
                f"   理由: {section.rationale}"
            )
        
        body_text = "\n\n".join(sections)
        
        return (
            f"标题: {self.title}\n"
            f"总时长: {self.total_duration}秒\n"
            f"关键词: {', '.join(self.keywords)}\n"
            f"需要续写: {'是' if self.need_write_next else '否'}\n"
            f"备注: {self.notes}\n\n"
            f"剧本内容:\n{body_text}"
        )


from typing import List
from pydantic import BaseModel, Field, conint


class Segment(BaseModel):
    item_id: Optional[str] = None
    title: str = Field(..., description="镜头标题/小节名")
    duration_s: conint(ge=1) = Field(..., description="镜头时长（秒）")
    shot: str = Field(..., description="景别（近景/中景/远景/特写等）")
    camera_move: str = Field(..., description="运镜（静止/推拉/摇移/跟拍/变焦等）")
    location: str = Field(..., description="场景（室内/居家/户外/店铺等）")
    props: List[str] = Field(default_factory=list, description="道具/产品/辅料")
    visual: str = Field(..., description="画面动作与细节（可拍）")
    onscreen_text: str = Field("", description="屏幕字幕/要点（可为空）")
    audio: str = Field("", description="口播/对白/音效（可为空）")
    music: str = Field("", description="BGM 建议（可为空）")
    transition: str = Field("", description="转场到下一镜头（可为空）")
    compliance_notes: str = Field("", description="合规注意事项（可为空）")


class SubSection(BaseModel):
    sub_section: str = Field(..., description="子段落标题")
    narrative_goal: str = Field(..., description="该子段落的叙事目标")
    segments: List[Segment] = Field(..., min_items=1, description="镜头拆分列表")


class Section(BaseModel):
    item_id: Optional[str] = None
    section: str = Field(..., description="大段落标题")
    rationale: str = Field(..., description="该段落的创作/算法/情绪设计 rationale")
    sub_sections: List[Segment] = Field(..., min_items=1, description="镜头列表")
    duration: conint(ge=1) = Field(..., description="本段落总时长（秒），必须与 sub_sections.duration_s 之和一致")


class TotalVideoScript(BaseModel):
    title: str = Field(..., description="整条视频标题")
    total_duration: int = Field(
        ...,
        ge=1,
        description="总时长（秒）"
    )
    keywords: List[str] = Field(default_factory=list, description="关键词（去重后）")
    sections: List[Section] = Field(default_factory=list, description="完整分镜/镜头脚本（L2）")
    notes: str = ""


class ProgressEvent(BaseModel):
    phase: str = ""
    type: str
    data: dict[str, Any] = Field(default_factory=dict)

