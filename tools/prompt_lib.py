"""이미지 생성 프롬프트 공통 문구 · 복식 고증 사전 (gen_asset_manifest.py 가 사용).

프롬프트 = [종류별 본문] + [복식 고증(인물만)] + STYLE_COMMON + [종류별 규격 꼬리]   /   negative = NEG_COMMON + 종류별 추가
배경 연도: 1861년(철종 12, 대동여지도 간행). 1861년 이전 시대 인물은 그 시대 복식을 쓴다.
"""

STYLE_COMMON = ("Joseon-era Korean ink-and-wash painting (sumukchaesaek) on aged hanji mulberry paper, "
                "muted mineral pigments (malachite green, azurite blue, ochre, cinnabar red, ink black), "
                "confident brush strokes with dry-brush texture, soft paper grain, restrained palette, "
                "in the manner of Kim Hong-do and Jeong Seon")

NEG_COMMON = ("photorealistic, 3d render, anime, chibi, western fantasy, neon, glossy plastic, text, watermark, signature, "
              "modern clothing, Chinese Qing costume, Manchu queue hairstyle, Japanese kimono, samurai armor, hakama, "
              "hanfu with crossed wide sleeves of Ming court, Japanese katana")

# 종류별 규격 꼬리(구도·비율) 와 negative 추가분
KIND_TAIL = {
    "icon":       ("single object centered, plain warm hanji background, soft ambient occlusion, clean silhouette, game item icon, 1:1 --ar 1:1 --style raw", "multiple objects, hands, cluttered background"),
    "portrait":   ("half-length portrait, three-quarter view, calm dignified expression, plain hanji background with faint ink wash, 4:5 --ar 4:5 --style raw", "extra fingers, deformed hands, multiple people"),
    "region_map": ("top-down cartographic view in the style of the 1861 Daedongyeojido woodblock map, mountain ranges as sawtooth ridges, rivers as double lines, "
                   "follow the provided relief guide exactly for coastline and ridges, no labels, 16:9 --ar 16:9 --style raw", "perspective view, labels, grid lines, compass rose, modern roads"),
    "parallax":   ("horizontal seamless side-scrolling layer, left and right edges tile, transparent sky above the layer, 8:3 --ar 8:3 --style raw", "characters, buildings in the foreground unless stated, vignette"),
    "battle_bg":  ("wide side-view battle stage, clear flat ground band in the lower third for characters, 8:3 --ar 8:3 --style raw", "characters, text"),
    "sprite":     ("full body side view facing right, walking cycle reference sheet, 8 frames in one row, consistent proportions, transparent background --ar 8:1 --style raw", "background scenery, cropped feet"),
    "marker":     ("small emblem icon, bold readable silhouette at 64px, thick ink outline, transparent background, 1:1 --ar 1:1 --style raw", "fine detail, text"),
    "overworld":  ("whole Korean peninsula in the style of the Daedongyeojido, vertical composition, eight provinces subtly tinted, 7:10 --ar 7:10 --style raw", "labels, modern borders"),
    "minigame":   ("flat frontal composition filling the frame, even lighting, 1:1 --ar 1:1 --style raw", "text, frame border"),
    "scene":      ("visual-novel background, eye-level wide establishing shot, empty of people, lower quarter kept calm for a dialogue box, 16:9 --ar 16:9 --style raw", "people, characters, text, UI"),
}

# ── 복식 고증 ────────────────────────────────────────────────
COSTUME = {
    "civil_official": "Joseon civil official in black dallyeong robe with round collar and crane rank badge (hyungbae), black samo winged hat, gakdae belt",
    "scholar":        "Joseon seonbi scholar in white or pale jade dopo overcoat with tie sash, black horsehair gat hat with wide brim, beoseon socks",
    "military":       "Joseon military officer in dark blue cheollik pleated robe, jeollip felt hat with feather and beads, dongae quiver and hwando sword at the waist",
    "tiger_hunter":   "Joseon tiger-hunting elite soldier (chakho gapsa) in cheollik robe with leg wraps, jeollip hat, bow and spear",
    "monk":           "Korean Buddhist monk with shaved head, grey jangsam robe with a red-brown kasaya over the left shoulder, wooden prayer beads",
    "dosa":           "Korean Taoist hermit in white hakchangui robe with black trim, bokgeon cloth cap, crane-feather fan",
    "merchant":       "Joseon bobusang peddler in undyed cotton jeogori and baji, paeraengi bamboo hat with white cotton balls, jige A-frame carrier on the back",
    "laborer":        "Joseon commoner craftsman in undyed hemp jeogori and baji with rolled sleeves, white cloth headband, straw jipsin sandals",
    "hunter":         "Joseon mountain musketeer in padded cotton clothes, fur vest, matchlock musket, straw sandals with leg wraps",
    "boatman":        "Joseon boatman in rough cotton jeogori and knee-rolled baji, straw hat, bamboo pole",
    "innkeeper":      "Joseon tavern keeper woman in short cotton jeogori, long chima skirt with apron, hair in a low jjok bun with a wooden binyeo pin",
    "noblewoman":     "Joseon yangban woman in long-sleeved jeogori with colored collar and ottgoreum ribbon, full floor-length chima, hair in a low jjok bun with jade binyeo pin",
    "commoner_woman": "Joseon commoner woman in short white cotton jeogori and indigo chima, hair in a low jjok bun, no jewelry",
    "maiden":         "unmarried Joseon girl in yellow jeogori and red chima, single long braid tied with a red daenggi ribbon",
    "gisaeng":        "Joseon gisaeng in very short fitted jeogori and voluminous layered chima, large braided trae-meori hairstyle, as in Shin Yun-bok genre paintings",
    "male_disguise":  "Joseon woman disguised as a male scholar-general, dopo robe and gat hat, armor vest (dugeonggap) over it",
    "shaman":         "Korean mudang shaman in red cheollik and blue kwaeja vest, jeollip hat, brass bells and fan",
    "underworld":     "Korean underworld messenger (jeoseung chasa) in black cheollik robe, wide black gat hat, red cord, pale face",
    "goguryeo":       "Goguryeo warrior noble as in Goguryeo tomb murals, dotted-pattern jeogori belted at the waist, wide trousers gathered at the ankle, jeolpung cap with bird feathers",
    "baekje":         "Baekje general in lamellar iron armor over a long red robe, Baekje-style crested helmet",
    "silla":          "Silla-era Korean, Silla aristocratic robe with wide sleeves, gilt-bronze ornaments",
    "silla_monk":     "Silla-era Korean Buddhist monk, shaved head, simple ochre robe, staff",
    "goryeo":         "Goryeo official in dark green gwanbok robe and black bokdu hat with long horizontal wings",
    "cheoyong":       "Cheoyong mask figure from Silla legend: red-faced mask, samo hat decorated with peonies and peaches, bright robe of five directional colors",
    "princess_myth":  "Korean shamanic goddess Bari in white ceremonial robe with multicolored saekdong sleeves, holding a willow branch",
    "royal_scholar":  "early Joseon high official in red dallyeong robe with rank badge, black samo hat",
    "outlaw":         "Joseon hero outlaw in dark blue dopo robe, black gat hat, bamboo staff, confident pose",
    "yangban_poor":   "impoverished Joseon scholar in patched worn dopo robe, battered gat hat",
    "celestial":      "Joseon novel protagonist of celestial origin, white robe with cloud patterns, jade hairpin, faint aura",
    "jeju_merchant_woman": "late 18th-century Jeju island merchant woman in her fifties, white cotton jeogori and dark chima with a Jeju galot (persimmon-dyed) apron, hair in a low jjok bun with a plain wooden binyeo, calm resolute face, holding an abacus and a ledger",
    "eosa":           "Joseon royal secret inspector (amhaeng eosa) in shabby dopo robe hiding a horse tablet (mapae), torn gat hat",
}

COMPANION_COSTUME = {
    "착호갑사": "tiger_hunter", "정약용": "scholar", "문익점": "goryeo", "박지원": "scholar", "심마니": "laborer", "정도전": "royal_scholar",
    "채제공": "civil_official", "김정희": "scholar", "신숙주": "royal_scholar", "장영실": "civil_official", "이천": "military", "김정호": "scholar",
    "이순신": "military", "남이": "military", "권율": "military", "황진이": "gisaeng", "안견": "scholar", "김홍도": "scholar",
    "신사임당": "noblewoman", "허준": "civil_official", "이제마": "scholar", "채규서": "civil_official", "정약종": "scholar",
    "을지문덕": "goguryeo", "연개소문": "goguryeo", "계백": "baekje", "강림도령": "underworld", "뱃사공": "boatman",
    "사명대사": "monk", "원효대사": "silla_monk", "의상대사": "silla_monk", "서산대사(휴정)": "monk", "보조국사 지눌": "monk",
    "바리공주": "princess_myth", "전우치": "dosa", "홍길동": "outlaw", "처용(處容)": "cheoyong",
    "대장장이": "laborer", "백정": "laborer", "약초꾼": "laborer", "옹기장이": "laborer", "보부상(부상)": "merchant", "역졸(마부)": "laborer",
    "산포수": "hunter", "짚신장이": "laborer", "주모": "innkeeper", "시골 훈장": "scholar", "뗏목사공": "boatman", "채석 광부": "laborer",
    "옻칠장": "laborer", "한지장이": "laborer", "석공(석수)": "laborer",
    "박씨부인": "noblewoman", "심청": "maiden", "성춘향": "maiden", "이몽룡": "eosa", "흥부": "yangban_poor", "배비장": "civil_official",
    "허생": "yangban_poor", "조웅": "military", "유충렬": "celestial", "양소유": "scholar", "숙향": "celestial", "장화": "maiden",
    "홍계월": "male_disguise", "남사고": "dosa", "혜원 신윤복": "scholar",
}
HERO_COSTUME = {"cls_eosa": "eosa", "cls_merchant": "merchant", "cls_dosa": "dosa"}

ENEMY_DESC = {
    "en_bandit": "Joseon mountain bandit (hwajeok) in ragged hemp clothes and headband, wooden club",
    "en_galjae_bandit": "Joseon bandit chief of Galjae pass, scarred face, stolen cheollik robe, hwando sword",
    "en_pirate": "coastal raider crew on a small wooden boat, rough cotton clothes, hooked spears",
    "en_cultist": "cult followers in hooded hemp robes with red talisman sashes, in a cave",
    "en_yeokcheon_disciple": "heretical sorcerer disciple in black hakchangui robe with inverted trigram embroidery",
    "en_wolf": "pack of grey Korean wolves in snowy pine forest", "en_tiger": "Korean Amur tiger, sansin guardian, as in Joseon minhwa tiger paintings",
    "en_dokkaebi_small": "small mischievous Korean dokkaebi goblin with one horn and a spiked club, playful, not Japanese oni",
    "en_dokkaebi": "Korean dokkaebi goblin with a magic club (dokkaebi bangmangi), roguish grin, not Japanese oni",
    "en_yagwanggwi": "yagwanggwi, a New-Year night ghost that steals shoes, glowing faint body",
    "en_ghost": "Korean maiden ghost (cheonyeo gwisin) in white sobok mourning dress, long loose black hair",
    "en_spirit_minion": "wisps of resentful spirits in white tattered cloth", "en_arang": "Arang, wronged maiden spirit of Miryang, white dress, bleeding hairpin",
    "en_jirisan_sanshin": "corrupted mountain god of Jirisan, old man with white beard, tiger companion, darkened aura",
    "en_gumiho": "Korean nine-tailed fox (gumiho) half transformed from a woman in hanbok",
    "en_cheolgwi": "iron-eating demon made of rusted iron plates", "en_bulgasari": "Bulgasari, iron-eating chimera with bear body, elephant nose, rhinoceros eyes",
    "en_yeokcheon": "the heaven-defying demon lord, colossal shadow in ink with inverted taeguk",
    "en_lava_serpent": "young imugi serpent of volcanic rock and lava", "en_imugi": "imugi, a great serpent that has not yet become a dragon, holding no pearl",
    "en_jeju_dochaebi": "Jeju island dochaebi goblin, small fiery sprite from Jeju folklore, black basalt stones around, playful and mischievous, not Japanese oni",
    "en_jeju_yeonggam": "Yeonggam, the Jeju dokkaebi deity of fishermen from the Yeonggam-nori shaman play, wearing a paper mask and ragged robe, torch-lit night beach",
    "en_hwangdangseon": "crew of a foreign 'hwangdangseon' strange ship raiding a Joseon coast in the 19th century, rough sailors with cutlasses, a dark sailing ship behind",
    "en_majeok": "mounted northern horse bandits (majeok) beyond the Tumen river, fur hats and padded coats, horses in snowy steppe",
    "en_boar_herd": "herd of wild boars charging through a Korean pine forest",
    "en_bear": "Asian black bear (bandal-gom) with a white crescent on its chest, standing in a Korean mountain forest",
    "en_heukryong": "black dragon of Cheonji lake on Baekdu mountain, holding a yeouiju pearl, Korean dragon with four claws",
}
REGION_SCENE = {
    "MAP_01": "Imjin river valleys and Songak mountain near Gaeseong", "MAP_02": "Han river plains, Suwon fortress walls, Namhan mountain",
    "MAP_03": "Geumgang mountain granite peaks and east sea coast", "MAP_04": "Odae and Taebaek ranges, rafting rivers of Jeongseon",
    "MAP_05": "Songni mountain and Namhan river terraces", "MAP_06": "Geum river, Gyeryong mountain and west sea mudflats",
    "MAP_07": "Honam wide rice plains and Naejang mountain maples", "MAP_08": "south-west archipelago, tidal straits and Jiri mountain slopes",
    "MAP_09": "Andong river bends, Sobaek ridges, Gyeongju burial mounds", "MAP_10": "Nakdong delta, Tongyeong harbour, Jiri mountain",
    "MAP_11": "Jaeryeong plain and Guwol mountain", "MAP_12": "Jangsan cape cliffs and Ongjin coast",
    "MAP_13": "Daedong river, Pyongyang walls and Myohyang mountain", "MAP_14": "Amnok river cliffs and northern forts",
    "MAP_15": "Hamheung plain and Gaema plateau", "MAP_16": "Baekdu mountain, larch forests and Duman river snowfields",
    "MAP_17": "Halla mountain, oreum cones, basalt stone walls and volcanic coast",
}
CLIMATE = {"temperate": "early autumn light", "cold": "crisp late-autumn air", "warm": "humid summer haze", "frigid": "deep winter snow"}
