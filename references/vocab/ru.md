# Russian Vocabulary

Use this reference for Russian Seedance prompt wording, role binding, and compact translation. Binding is a separate typed step: the selected profile preserves an external opaque handle, derives an evidenced media ordinal, or uses structured roles with no token. Never translate provider syntax.

| Function | Russian | English meaning |
|---|---|---|
| Request role | назначить начальное изображение первым кадром | structured first-frame role; no invented prompt token |
| Request role | назначить конечное изображение последним кадром | structured last-frame role; no invented prompt token |
| Binding clause | `задает персонажа` | defines the character |
| Binding clause | `задает атмосферу сцены` | defines scene mood |
| Binding clause | `только движение камеры` | provides camera movement only |
| Binding clause | `задает ритм действия` | provides action rhythm |
| Binding clause | `задает темп и настроение` | provides tempo and mood |
| FirstLastFrame | `сохранить первый кадр без изменений` | keep first frame unchanged |
| FirstLastFrame | `естественный переход к последнему кадру` | natural transition to final frame |
| FirstLastFrame | `непрерывное движение без монтажного скачка` | continuous motion, no jump cut |
| FirstLastFrame | `последний кадр является целевым финалом` | final frame is the target endpoint |
| Camera | `фиксированный средний план` | locked medium shot |
| Camera | `медленный наезд камеры` | slow push-in |
| Camera | `отъезд с раскрытием пространства` | pull back to reveal the space |
| Camera | `плавное боковое сопровождение` | stable lateral tracking |
| Camera | `макросъемка крупным планом` | macro close-up |
| Camera | `кадр через плечо` | over-the-shoulder shot |
| Camera | `нижний ракурс` | low-angle shot |
| Camera | `верхний ракурс` | high-angle shot |
| Camera | `круговой облет объекта` | orbit around the subject |
| Camera | `ручная камера с легким дыханием` | handheld camera with slight breathing sway |
| Shot | `среднекрупный план` | medium close-up |
| Shot | `широкий общий план` | wide establishing shot |
| Shot | `профиль в три четверти` | three-quarter profile |
| Lens | `сжатая перспектива телеобъектива` | telephoto compression |
| Lens | `широкоугольное ощущение пространства` | wide-angle spatial feel |
| Lens | `фокус переходит от размытия к резкости` | focus resolves from blur to sharpness |
| Lighting | `мягкий контровой свет` | soft backlight |
| Lighting | `теплый практический источник` | warm practical light |
| Lighting | `теплый практический свет слева` | warm practical light from left |
| Lighting | `холодная лунная контурная подсветка` | cool moon rim light |
| Lighting | `объемный свет через легкий туман` | volumetric light through mist |
| Lighting | `мокрый асфальт отражает неон` | wet asphalt reflects neon |
| Motion | `туман расходится вокруг шагов` | fog spreads around the feet |
| Motion | `капли соединяются и стекают вниз` | droplets merge and slide down |
| Motion | `медленно поворачивает голову и замирает` | slow head turn and stop |
| Motion | `ткань естественно движется от жеста` | fabric moves naturally with action |
| VFX | `золотые частицы поднимаются и рассеиваются` | gold particles rise and dissipate |
| VFX | `синие электрические дуги ползут по краю` | blue arcs crawl along the edge |
| VFX | `световой блик проходит по поверхности материала` | light sweep travels across material |
| Audio | `одна короткая четкая реплика` | one short clear spoken line |
| Audio | `без музыки, только тихий фон` | no music, ambience only |
| Audio | `во время реплики камера неподвижна` | locked camera during dialogue |
| Audio | `шаги попадают в ритм` | footsteps hit the beat |
| Text | `без лишних субтитров, текста и водяных знаков` | no extra subtitles, text, or watermarks |
| Editing | `продолжить кадр` | continue the shot |
| Editing | `продлить на 5 секунд` | extend by five seconds |
| Editing | `заменить только неудачный фрагмент` | replace only the failed segment |
| Constraint | `сохранить логотип, этикетку, форму и цвет без изменений` | preserve logo, label, shape, and color |
| Constraint | `меняются только движение, свет и камера` | change only movement, light, and camera |
| Constraint | `не копировать людей, место или бренды` | do not copy people, place, or brands |
| Safety | `заменить на оригинального персонажа` | change to an original character |
| Safety | `использовать только авторизованный референс` | use only authorized reference |
| Safety | `сохранить творческую функцию без защищенной личности` | preserve creative function, not protected identity |

## Compact Template

After the typed reference binding: `— референс; сохранить [персонажа/продукт/логотип] без изменений. Меняются только [движение/свет/камера]. Камера: [одно движение]. Звук: [аудиосигнал].`

## Russian Dialogue Notes

Test the exact surface, model version, spoken line, voice path, and framing. The retained evidence does not establish a universal Russian-vs-other-language ranking, dialogue limit, or accent outcome.

| Rule | Practice |
|---|---|
| Короткие реплики | Start with one short performable line, such as `Она тихо говорит: «Я нашла его»`, then expand only after a controlled pass |
| Кириллица vs транслит | Use the user's intended written/spoken form; treat Cyrillic, transliteration, or hybrid variants as separate tests rather than a universal fallback order |
| Один говорящий | Start with one named speaker and stable face framing while reviewing lip-sync |
| Полная озвучка | For a long voiced piece, plan a post-dub path and compare it with short in-model tests (see `audio-post-delivery.md`) |
| Доступ и провайдер | Route region, model-name, price, and availability questions through the current surface/source gate |
| Длительность реплики | Measure spoken duration and articulation load; no retained universal word maximum is available |
| Аудио-референс | Where the exact operation supports an authorized spoken-voice reference, test it as a voice/timing source without assuming exact reproduction |

## Slop Traps

Заменяйте абстрактные оценки наблюдаемыми элементами (глагол камеры + скорость + точка зрения, источник света + направление + поведение), чтобы указание было легче сравнивать и исправлять. Эффект на генерацию проверяйте при одинаковых входных условиях.

| Штамп | Пишите вместо него |
|---|---|
| `кинематографичный` | крупность, движение камеры, источник света и цветокор: `широкий общий план, медленный наезд, низкое теплое солнце, тил-энд-оранж` |
| `эпичный` | физический масштаб: размер толпы, расстояние до объекта, высота сооружения |
| `потрясающий / захватывающий` | тот единственный контраст или момент раскрытия, который это оправдывает |
| `красивый` | цвет, фактура, материал, поведение света |
| `шедевр / высокое качество / 8K` | удалить; качество не запрашивается, разрешение — это настройка |
| `атмосферный` | физические элементы атмосферы: `тонкий туман, отражения на мокром асфальте, тихий фон` |
| `драматичный` | мизансцена, тень, тишина или давление камеры |
| `волшебный` | поведение частиц, источник свечения, траектория |
| `невероятно детализированный` | две детали, которые действительно важны, названные прямо |
| `динамичный` | конкретное движение, его скорость и конечная точка |
| `профессиональный` | контролируемый свет на продукте, чистый фон, стабильная камера |
