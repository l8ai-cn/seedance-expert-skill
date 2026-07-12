# Chinese Vocabulary

Use this reference when the requested prompt or production handoff is in Chinese. Write concise, observable production direction without assuming that shorter wording is inherently more effective. Binding is a separate typed step: the selected profile preserves an external opaque handle, derives an evidenced media ordinal, or uses structured roles with no token. Never translate provider syntax.

| Function | Chinese | English meaning |
|---|---|---|
| Request role | 将提供的起始图像设为首帧 | structured first-frame role; no invented prompt token |
| Request role | 将提供的目标图像设为尾帧 | structured last-frame role; no invented prompt token |
| Binding clause | `锁定主体身份` | locks subject identity |
| Binding clause | `仅参考场景氛围` | provides scene mood only |
| Binding clause | `仅参考运镜` | provides camera movement only |
| Binding clause | `参考动作节奏` | provides action rhythm |
| Binding clause | `参考节奏和氛围` | provides tempo and mood |
| FirstLastFrame | `首帧保持不变` | keep first frame unchanged |
| FirstLastFrame | `自然过渡到尾帧` | transition naturally to final frame |
| FirstLastFrame | `中间动作连续，不跳切` | continuous in-between motion, no jump cut |
| FirstLastFrame | `以尾帧为最终画面目标` | use final frame as the target image |
| Camera | `缓慢推镜` | slow push-in |
| Camera | `镜头后拉揭示空间` | pull back to reveal the space |
| Camera | `横向稳定跟拍` | stable lateral tracking |
| Camera | `轨道平移` | slider / dolly lateral move |
| Camera | `固定中景` | locked medium shot |
| Camera | `微距特写` | macro close-up |
| Camera | `低角度仰拍` | low-angle shot |
| Camera | `高角度俯拍` | high-angle shot |
| Camera | `过肩镜头` | over-the-shoulder shot |
| Camera | `弧形绕摄` | arc orbit shot |
| Camera | `手持镜头，轻微呼吸晃动` | handheld shot with slight breathing sway |
| Shot | `中近景` | medium close-up |
| Shot | `远景定场镜头` | wide establishing shot |
| Shot | `四分之三侧脸` | three-quarter profile |
| Lens | `长焦压缩空间` | telephoto compression |
| Lens | `广角空间感` | wide-angle spatial feel |
| Lens | `焦点从模糊过渡到清晰` | focus resolves from blur to sharpness |
| Lighting | `柔和侧逆光` | soft side backlight |
| Lighting | `暖色实用灯` | warm practical light |
| Lighting | `左侧暖色实用灯` | warm practical light from left |
| Lighting | `冷色月光轮廓光` | cool moon rim light |
| Lighting | `体积光穿过薄雾` | volumetric light through mist |
| Lighting | `潮湿地面反射霓虹` | wet ground reflects neon |
| Motion | `脚步带动薄雾扩散` | footsteps disturb fog |
| Motion | `水珠聚合后沿表面下滑` | droplets merge and slide down |
| Motion | `缓慢转头并停住` | slow head turn and stop |
| Motion | `衣料随动作自然摆动` | fabric moves naturally with action |
| VFX | `金色粒子升起后消散` | gold particles rise and dissipate |
| VFX | `蓝色电弧沿边缘游走` | blue arcs crawl along the edge |
| VFX | `光线扫过材质表面` | light sweep travels across material |
| Audio | `一句短而清晰的对白` | one short clear spoken line |
| Audio | `无配乐，仅低环境声` | no music, low ambience only |
| Audio | `对白期间镜头固定` | locked camera during dialogue |
| Audio | `脚步声卡点` | footsteps hit the beat |
| Text | `不要新增字幕、水印或无关文字` | no new subtitles, watermark, or unrelated text |
| Editing | `接着拍` | continue the shot |
| Editing | `延长 5 秒` | extend by five seconds |
| Editing | `只替换失败片段` | replace only the failed segment |
| Constraint | `严格保持logo、标签、形状和颜色不变` | preserve logo, label, shape, and color |
| Constraint | `仅改变动作、光线和镜头` | change only action, light, and camera |
| Constraint | `不复制人物、场景或品牌` | do not copy person, scene, or brand |
| Safety | `改为原创角色` | change to an original character |
| Safety | `仅使用已授权参考` | use only authorized references |
| Safety | `保留创意功能，不保留受保护身份` | preserve creative function, not protected identity |

## Compact Template

在类型化引用绑定后的独立文本片段中，用标点分隔，不把语法黏在未知句柄上：`：授权参考。严格保持[主体/产品/脸部/标志]不变；仅加入[动作/光线/镜头变化]。镜头：[一个动作]。声音：[音效或环境声]。`

## Timeline Template

社区常用的长提示词骨架（即梦/Dreamina 平台，约 8 秒以上时使用；field-observed）。引用位置必须由当前平台配置的类型化绑定片段解析；下面不规定任何字面标签：

```
【风格】[媒介、质感、色调，一句话]
【时间轴】0-3s：[画面+镜头+音效]；3-6s：[画面+镜头+音效]；6-10s：[画面+镜头+音效]
【声音】[对白/环境声/音效/无配乐]
【参考】身份绑定：锁定主体身份；视频绑定：仅参考运镜；音频绑定：仅参考节奏
```

## Sequence and Continuation Phrases

Use these when the Chinese prompt is part of a v6 sequence project, continuation, or localized delivery workflow.

| Function | Chinese | English meaning |
|---|---|---|
| Role | `本项目状态以已接受视频为准` | accepted footage is the project truth |
| Role | `从上一段真实结尾继续` | continue from the actual previous ending |
| Role | `不要重演上一段动作` | do not replay the previous action |
| Role | `本段只拍当前任务` | this clip shows only the current task |
| Role | `后续剧情暂不出现` | future story beats do not appear yet |
| FirstLastFrame | `以上一段尾帧为起点` | use previous final frame as starting point |
| FirstLastFrame | `以新尾帧状态收束` | settle into the new final state |
| Motion | `保持上一段开放动作方向` | preserve previous open motion vector |
| Motion | `动作从静止状态开始` | action starts from a still state |
| Editing | `作为 Clip 02 的接续提示词` | continuation prompt for Clip 02 |
| Editing | `只修复尾部漂移，不改前半段` | repair only tail drift, not the first half |
| Constraint | `已完成动作不得重复` | completed actions must not repeat |
| Constraint | `未发生内容不得提前出现` | unshown future events must not appear early |
| Text | `画面保持无文字，字幕后期添加` | keep image textless; subtitles added in post |
| Text | `中文标题和法务文案在剪辑中添加` | Chinese titles and legal copy added in edit |
| Safety | `保留创意功能，替换为原创身份` | preserve creative function with original identity |

## Dialogue Notes (对白注意事项)

Field-observed from 2026 community testing; test the exact surface, model version, spoken language, line, voice path, and framing. The retained evidence does not establish that one language is universally better than another. Hands-on reports still describe 语音错乱 and 字幕乱码 on some tasks, so budget review and retakes.

- 台词格式：角色名 + 动作 + 冒号 + 引号内台词。Count characters/syllables, not "words"; keep to one short clause.
- 先确认当前平台与操作是否提供并启用了唇形同步；不要从其他界面的旧截图或教程推断当前开关状态。
- Inline audio tags are field-reported on some surfaces: 在台词末尾加方括号提示音色与音效，例如 `"领旨" [低沉男声][编钟余音]`。This is surface-specific syntax; use it only when the selected profile or current surface evidence supports it.

## V7 中英文配对边界

当输入包含已验证的 scene IR 与中英文配对目录时，`scripts/prompt_compile.py` 只渲染目录中已审定的中文表达，`scripts/semantic_lint.py` 检查结构一致性。编译器不翻译 scene IR。中英文输出必须保持相同的实体 ID、事件顺序、因果关系、镜头语义、音频关联和约束。V7-07 暂不编译对白或旁白，因为当前 IR 没有精确台词合同。实体名称必须稳定，不得自动省略主语或推断 `他`、`她`。缺少中文表达、语义冲突或角色不明时必须停止。

## Slop Traps

把抽象“感觉词”改写为可观察的材质、光线、色彩、空气和动作，能让提示词更容易审阅、比较和修改。它是否改善某个平台上的生成结果，仍需用相同输入做实际测试。

| 套话 | 改写为 |
|---|---|
| `电影感` | 写出景别、运镜、光源和调色：`宽幅远景，缓慢推镜，低角度暖阳，低饱和青橙调` |
| `氛围感` | 写出制造氛围的物理元素：`薄雾、逆光轮廓、湿润地面反光、低环境声` |
| `高级感` | 写出光线与材质行为：`柔和侧光、受控反光、干净背景、金属拉丝纹理` |
| `大片感` | 写出物理规模：人群数量、镜头距离、建筑高度 |
| `质感`（单独使用） | 指明哪种质感：`磨砂玻璃、丝绒吸光、纸张纤维` |
| `震撼` | 写出造成震撼的那一个画面对比或揭示 |
| `唯美` | 写出色彩、构图与光的具体行为 |
| `史诗级` | 删除，或换成具体的空间尺度与人数 |
| `超高清 / 8K / 4K` | 删除；分辨率是参数，不是描述 |
| `杰作 / 顶级品质` | 删除；质量不是请求出来的 |
| `绝美` | 写出最重要的那一个视觉细节 |
| `酷炫转场` | 写出转场名称：`匹配剪辑、硬切、甩镜` |
