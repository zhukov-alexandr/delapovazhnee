// The lines of the song «19», revealed one at a time as the player crosses each
// points_per_line threshold (see gamestate.js: nextRevealIndex). When the last
// line is revealed, boot.js shows the "song complete" popup with the full text.
// Each entry carries a fixed "\n" break so every lyric renders as exactly TWO
// display lines everywhere (sky cloud, opened-lines viewer, song-complete popup)
// — no automatic word-wrap guessing.
export const LYRICS = [
  "Я встретил тебя\nна Курортном проспекте",
  "Такой неуклюжий,\nа ты улыбнулась",
  "Мы будто родились\nна разных планетах",
  "Ты ярко сияешь,\nя робко сутулюсь",
  "«Пойдём же быстрей» —\nты вдруг мне сказала",
  "Кто встретит закат,\nесли нас там не будет?",
  "Я чувствовал только,\nкак вспыхнуло пламя",
  "И будто мы —\nсамые близкие люди",
  "Девятнадцать часов,\nсередина июля",
  "В закатное солнце\nна пляже смотрю я",
  "Мечтаем с тобой\nнавсегда здесь остаться",
  "И пусть снова нам\nбудет по девятнадцать",
];
