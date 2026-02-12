# application.py
import asyncio

from agent.compass_agent import CompassChoicesAgent
from agent.total_workflow import total_script_infer
from schema.base import ProgressEvent
from core.compass import CompassSelection

content = """
    Hello Kitty餐盘 Amazon 产品介绍视频，无声音，无台词，重场景以及人群调性
"""

async def main():
    
    def on_progress(evt: ProgressEvent):
        if evt.type == "iter_success":
            stage = evt.data["stage"]
            stage_result_json = evt.data.get("result_json")  # 或 evt.data.get("result") 是 dict
            print(stage, stage_result_json)

        # 你也可以在这里做更复杂的：写文件、推 websocket、更新 UI 等
        print(evt)

    result = await total_script_infer(
        content=content,
        platform="抖音",
        max_duration=30,
        language="中文",
        on_progress=on_progress,
        images=[
            "https://www.supercutekawaii.com/wp-content/uploads/dinner-collection-set.jpg"
        ]
    )
    
if __name__ == "__main__":
    asyncio.run(main())