// Game i18n: RU (default) + 中文, mirroring the /home landing's approach
// (data-i18n attributes + a JS dictionary + RU/中文 buttons persisted in
// localStorage). The language key `dp_lang` is SHARED with the landing, so a
// visitor who picked 中文 there gets the Chinese game too. The landing also has
// EN, the game doesn't — "en" falls back to RU here.
//
// Lyrics are NEVER translated in place: the RU original always shows, with the
// Chinese translation rendered UNDER each line (see LYRICS_ZH; index-aligned
// with LYRICS in lyrics.js).

export const LYRICS_ZH = [
  "我在库罗尔特大道上遇见了你",
  "我那么笨拙，你却对我微笑",
  "我们仿佛生在不同的星球",
  "你光芒四射，我却羞涩地驼着背",
  "“快点走吧”——你突然对我说",
  "如果我们不在，谁来迎接日落？",
  "我只感到心中燃起了火焰",
  "仿佛我们是彼此最亲近的人",
  "十九点整，七月中旬",
  "我在海滩上望着落日",
  "我们梦想永远留在这里",
  "愿我们再次回到十九岁",
];

export const I18N = {
  ru: {
    // Everything the RU page already says — listed so t() can flip BACK to RU
    // after switching, without a page rebuild.
    title: "Дела поважнее – Игра «19»",
    loading_title: "Загрузка игры",
    start_title: "ДЕЛА ПОВАЖНЕЕ – 19",
    welcome: "Кто не мечтает летом оказаться на красивом берегу? Выбирай героя и беги к своей мечте!",
    char_0: "Кирилл", char_1: "Никита", char_2: "Саша", char_3: "Костя",
    best: "Рекорд: ",
    manual_jump: "Пробел / тап — прыжок",
    manual_double_html: "<b>Двойной тап</b> — двойной прыжок, прыгаешь <b>выше</b>!",
    manual_catch: "Лови предметы в воздухе (+1)",
    manual_plov: "Плов возвращает 1 жизнь",
    manual_obstacles: "Перепрыгивай препятствия",
    play: "Играть",
    scores: "Рекорды",
    to_site: "На сайт",
    over_title: "Игра окончена",
    stat_score: "Счёт: ", stat_time: " · Время: ",
    name_placeholder: "Твоё имя",
    save_score: "Сохранить результат",
    saving: "Сохранение…",
    saved: "Сохранено ✓",
    retry: "Ещё раз",
    opened_lines: "Открытые строки",
    main_menu: "Главное меню",
    life_lost_title: "Ой!",
    points: "Очки: ",
    continue_: "Продолжить",
    lb_all: "Все",
    lb_close: "Закрыть",
    lb_empty: "Пока пусто — стань первым!",
    pause_title: "Пауза",
    opened_back: "Назад",
    opened_empty: "Пока ничего не открыто — набирай очки!",
    song_complete_title: "Ура, ты открыл все возможные строчки песни!",
    song_complete_presave: "Песня «19» выйдет 17 июля 2026! · Слушать",
    song_complete_next: "Играть дальше",
    cta_caption: "Дела поважнее – 19",
    cta_presave: "Слушать песню",
    presave_title: "Пресейв",
    presave_release: "Дела поважнее – 19",
    presave_row: "Пресейв",
    presave_saved: "Сохранено",
    reveal_label: "Открыта новая строка песни:",
    lives_left: (n) => {
      if (n % 10 === 1 && n % 100 !== 11) return `Осталась ${n} жизнь`;
      const form = (n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14)) ? "жизни" : "жизней";
      return `Осталось ${n} ${form}`;
    },
    err_default: "Недопустимое имя",
  },
  zh: {
    title: "Dela povazhnee – 游戏《19》",
    loading_title: "游戏加载中",
    start_title: "DELA POVAZHNEE – 19",
    welcome: "谁不想在夏天来到美丽的海滩？选择你的角色，向梦想奔跑吧！",
    char_0: "基里尔", char_1: "尼基塔", char_2: "萨沙", char_3: "科斯佳",
    best: "最高分：",
    manual_jump: "空格 / 点按——跳跃",
    manual_double_html: "<b>双击</b>——二段跳，跳得<b>更高</b>！",
    manual_catch: "接住空中的物品（+1）",
    manual_plov: "抓饭恢复 1 条命",
    manual_obstacles: "跳过障碍物",
    play: "开始游戏",
    scores: "排行榜",
    to_site: "官方网站",
    over_title: "游戏结束",
    stat_score: "得分：", stat_time: " · 时间：",
    name_placeholder: "你的名字",
    save_score: "保存成绩",
    saving: "保存中…",
    saved: "已保存 ✓",
    retry: "再来一次",
    opened_lines: "已解锁歌词",
    main_menu: "主菜单",
    life_lost_title: "哎呀！",
    points: "分数：",
    continue_: "继续",
    lb_all: "全部",
    lb_close: "关闭",
    lb_empty: "暂时没有记录——来当第一名吧！",
    pause_title: "暂停",
    opened_back: "返回",
    opened_empty: "还没有解锁歌词——快去得分吧！",
    song_complete_title: "恭喜！你解锁了所有歌词！",
    song_complete_presave: "歌曲《19》将于2026年7月17日发行！· 收听",
    song_complete_next: "继续游戏",
    cta_caption: "Dela povazhnee – 19",
    cta_presave: "收听歌曲",
    presave_title: "预存",
    presave_release: "Dela povazhnee – 19",
    presave_row: "预存",
    presave_saved: "已保存",
    reveal_label: "解锁了新的歌词：",
    lives_left: (n) => `还剩 ${n} 条命`,
    err_default: "名字不可用",
  },
};

// Server-side name-moderation errors arrive as RU text; map the known ones so
// the zh UI doesn't flash Cyrillic. Unknown messages fall through unchanged.
export const ERRORS_ZH = {
  "Только буквы, цифры, _ и -": "只能使用字母、数字、_ 和 -",
  "Недопустимое имя": "名字不合规",
  "Имя не длиннее 24 символов": "名字不能超过 24 个字符",
};

const LANG_KEY = "dp_lang"; // shared with /home (its EN falls back to RU here)

export function getLang(storage) {
  try {
    const v = (storage || localStorage).getItem(LANG_KEY);
    return v === "zh" ? "zh" : "ru";
  } catch (_) {
    return "ru";
  }
}

export function setLang(lang, storage) {
  try { (storage || localStorage).setItem(LANG_KEY, lang === "zh" ? "zh" : "ru"); } catch (_) { /* ignore */ }
}
