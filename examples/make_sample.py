#!/usr/bin/env python3
"""
生成一份模拟的母子聊天记录 examples/sample-messages.json，用来测试脚本和做演示。
全部是编的，没有任何真实的人。
"""
import json
import random
import sys

# Windows 默认控制台是 GBK，打不出 emoji；统一把输出切到 UTF-8（其他平台无影响）
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
from datetime import datetime, timedelta

random.seed(7)
start = datetime(2026, 3, 1, 7, 30)
end = datetime(2026, 8, 28, 22, 0)

HER_OPEN = [
    "吃饭了吗", "吃了没", "今天吃的什么", "你那边降温了 多穿点", "下雨了吗", "在干嘛",
    "周末回来吗", "什么时候放假", "最近忙不忙", "早点睡 别熬夜", "钱够不够花", "身体怎么样",
    "腰还疼不疼", "你爸说你上次电话里咳嗽 好点了吗", "到家了吗", "睡了吗", "今天忙吗",
    "你上次说脖子疼 去看了吗", "天气预报说你们那要下雪", "你那边台风大不大", "在吗",
    "你表姐生了 男孩", "家里的桂花开了 给你拍了一张", "你王阿姨问你有对象了吗",
    "买了点核桃给你寄过去了 收到说一声", "别老吃外卖", "早饭吃了没", "周末干什么了",
]
HER_FOLLOW = ["嗯 那你忙吧", "好 不打扰你了", "那你忙 没事", "好 早点睡", "嗯 注意身体", "知道了", "好的", "行 那你忙",
              "记得吃饭", "没事 就是问问", "没什么事", "你忙你的", "行吧", "嗯嗯"]
ME_SHORT = ["嗯", "好", "好的", "知道了", "在忙", "嗯嗯", "行", "吃了", "没事", "还行", "忙", "哦"]
ME_LONG = ["最近项目忙 周末可能加班 下个月看看", "吃了 公司楼下吃的", "没事妈 就是有点累 睡一觉就好了",
           "收到了 谢谢妈", "好的 我看看车票", "还没 这周末去", "知道了 你也早点睡", "妈我这边挺好的别担心"]
LINKS = ["这几种菜千万不能一起吃", "久坐伤腰 三个动作缓解", "颈椎病年轻化 看完这篇", "紧急通知 请扩散",
         "熬夜的危害 你不知道的十件事", "秋天要多吃这三样", "医生提醒 这样喝水最伤肾", "转发 好人一生平安"]
STICKERS_HER = ["[玫瑰]", "[握手]", "[太阳]", "[强]", "[抱拳]", "[合十]", "[微笑]"]
STICKERS_ME = ["[OK]", "[捂脸]", "[偷笑]"]

msgs = []
def add(dt, sender, type_="text", content="", dur=None):
    msgs.append({"ts": dt.strftime("%Y-%m-%dT%H:%M:%S"), "sender": sender, "type": type_, "content": content, "dur": dur})

t = start
while t < end:
    # 她开口的概率高
    who = "her" if random.random() < 0.78 else "me"
    hour = random.choice([6, 7, 7, 8, 12, 18, 20, 21, 21, 22]) if who == "her" else random.choice([12, 19, 22, 23, 23, 0, 1])
    t = t.replace(hour=hour, minute=random.randint(0, 59))
    if who == "her":
        kind = random.random()
        if kind < 0.12:
            add(t, "her", "link", random.choice(LINKS))
        elif kind < 0.24:
            add(t, "her", "voice", "", dur=random.randint(12, 60))
        elif kind < 0.30:
            add(t, "her", "image", "桂花/饭菜/天空的照片")
        else:
            add(t, "her", "text", random.choice(HER_OPEN))
        if random.random() < 0.35:
            add(t + timedelta(minutes=random.randint(1, 5)), "her", "sticker", random.choice(STICKERS_HER))
        # 我回不回
        r = random.random()
        if r < 0.32:
            pass  # 没回
        else:
            delay = timedelta(minutes=random.choice([3, 20, 45, 90, 180, 300, 420, 600, 900]))
            rt = t + delay
            if random.random() < 0.62:
                add(rt, "me", "text", random.choice(ME_SHORT))
            else:
                add(rt, "me", "text", random.choice(ME_LONG))
            if random.random() < 0.5:
                add(rt + timedelta(minutes=random.randint(1, 30)), "her", "text", random.choice(HER_FOLLOW))
                if random.random() < 0.3:
                    add(rt + timedelta(minutes=random.randint(31, 40)), "her", "sticker", random.choice(STICKERS_HER))
    else:
        add(t, "me", "text", random.choice(["妈 我这周末回去", "在吗", "妈 我发烧了 家里有退烧药吗", "妈 转我两千 下周还你", "妈 我到了"]))
        add(t + timedelta(minutes=random.randint(1, 8)), "her", "text", random.choice(["好 我去接你", "在的 怎么了", "发烧了？多少度 喝水了吗 去医院了没", "转了 不用还 你省着点", "好 到了就好"]))
        if random.random() < 0.4:
            add(t + timedelta(minutes=random.randint(9, 20)), "her", "voice", "", dur=random.randint(20, 58))
        if random.random() < 0.5:
            add(t + timedelta(minutes=random.randint(21, 60)), "me", "text", random.choice(["嗯", "好", "谢谢妈"]))
    t += timedelta(days=random.choice([1, 1, 1, 2, 2, 3]))

# 固定事件
add(datetime(2026, 5, 10, 21, 40), "me", "sticker", "[玫瑰]")                 # 母亲节：一个表情包
add(datetime(2026, 5, 10, 21, 41), "her", "text", "谢谢儿子 吃饭了吗")
add(datetime(2026, 6, 3, 0, 2), "her", "text", "生日快乐 儿子 妈妈永远爱你")     # 我生日 06-03
add(datetime(2026, 6, 3, 13, 20), "me", "text", "谢谢妈")
add(datetime(2026, 8, 14, 7, 15), "her", "text", "最近腰不太好 医生说要少干活")
add(datetime(2026, 8, 14, 19, 2), "me", "text", "注意休息")
add(datetime(2026, 8, 19, 20, 30), "her", "text", "打扰你了 你忙吧")
add(datetime(2026, 8, 25, 21, 10), "her", "text", "中秋回来吗")
add(datetime(2026, 4, 9, 20, 0), "her", "transfer", "转账")          # 只记次数，不记金额
add(datetime(2026, 4, 9, 22, 30), "me", "text", "收到了 谢谢妈")
add(datetime(2026, 7, 5, 19, 40), "me", "call_video", "视频通话", dur=14 * 60)
add(datetime(2026, 4, 12, 20, 10), "her", "call_video", "视频通话", dur=31 * 60)
add(datetime(2026, 5, 24, 20, 5), "her", "call_video", "视频通话", dur=27 * 60)

msgs.sort(key=lambda m: m["ts"])
data = {"me": "我", "her": "妈妈", "her_pronoun": "她", "source": "synthetic-demo", "messages": msgs}
json.dump(data, open("examples/sample-messages.json", "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
print(len(msgs), "条模拟消息 → examples/sample-messages.json")
