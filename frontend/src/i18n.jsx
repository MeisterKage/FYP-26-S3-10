/**
 * The interface in English, Mandarin (Simplified Chinese) and Bahasa Melayu.
 *
 * Articles are translated on the server (stored translations, labelled as AI
 * translated); this is the interface around them: navigation, menus, the
 * article page and its tools, and the reader-facing lists. Staff tools and the
 * long policy pages stay in English.
 *
 * The chosen language is a per-reader convenience kept in this browser, and
 * sent to the API with every request (?lang=zh) so lists and articles come
 * back translated where a translation exists.
 */
import { createContext, useContext, useEffect, useMemo, useState } from "react";

import { setApiLang } from "./api";

export const LANGUAGES = [
  { code: "en", label: "English", short: "EN", html: "en" },
  { code: "zh", label: "中文", short: "中文", html: "zh-Hans" },
  { code: "ms", label: "Bahasa Melayu", short: "BM", html: "ms" },
];
const STORE = "wn.lang";

const en = {
  "lang.label": "Language",
  "search.label": "Search articles by title, tag, or category", "search.placeholder": "Title, tag, or category",
  "search.how": "Keyword matching only. There is no semantic search and no personalised ranking. Results are ordered by credibility, then recency.",
  "search.none": "No results found", "search.noneText": "Nothing matched “{q}”. Try a broader word, or a category name.",
  "search.count": "{n} results", "search.countOne": "1 result",
  "search.prompt": "What are you looking for?", "search.promptText": "Search matches article titles, their tags, and category names.",
  "nav.browse": "Browse", "nav.search": "Search", "nav.pricing": "Pricing", "nav.signIn": "Sign in",
  "nav.createAccount": "Create account", "nav.yourWriting": "Your writing",
  "nav.reviewQueue": "Review queue", "nav.flagged": "Flagged", "nav.admin": "Administration",
  "browse.title": "Browse", "browse.topics": "Topics", "browse.countries": "Countries",
  "browse.allTopics": "All topics", "browse.allCountries": "All countries", "browse.home": "Home",
  "browse.aboutUs": "About us", "browse.howScoring": "How scoring works",
  "browse.digests": "Monthly digests", "browse.editors": "Our editors", "browse.pricing": "Pricing",
  "browse.featured": "Featured", "browse.featuredTitle": "This month’s most credible reporting",
  "browse.featuredNote": "Every section’s best-verified articles, and what we corrected.",
  "browse.close": "Close the menu",
  "account.menu": "Your account menu", "account.yourAccount": "Your account",
  "account.readingList": "Reading list", "account.liked": "Liked articles",
  "account.subscriptions": "Subscriptions", "account.signOut": "Sign out",
  "footer.tagline": "Sterling Wire. Every article scored by the same fixed rules.",
  "footer.aboutUs": "About us", "footer.howScoring": "How scoring works", "footer.allTopics": "All topics",
  "footer.digests": "Monthly digests", "footer.countries": "Countries", "footer.editors": "Our editors",
  "footer.subscriptions": "Subscriptions", "footer.search": "Search", "footer.privacy": "Privacy",
  "footer.terms": "Terms",
  "home.credibility": "Credibility", "home.trace": "Trace this score", "home.alsoToday": "Also today",
  "home.articles": "{n} articles", "home.inYourCategories": "In your categories",
  "home.fromFollowed": "From writers you follow", "home.nothing": "Nothing published yet",
  "home.nothingNote": "The first article appears here the moment an editor approves it.",
  "home.nothingCats": "Nothing in your categories yet",
  "home.nothingCatsNote": "Choose a few more interests and this page fills up.",
  "band.High": "High", "band.Moderate": "Moderate", "band.Low": "Low", "band.Disputed": "Disputed",
  "cred.accuracy": "{rate}% accuracy", "cred.new": "New contributor", "cred.score": "Credibility score",
  "cred.notReviewed": "Not yet reviewed", "cred.notReviewedLong": "Not yet reviewed by an editor",
  "cred.arithmetic": "Arithmetic, not prediction.", "cred.howCalculated": "How this is calculated",
  "ledger.accuracy": "Contributor accuracy", "ledger.sources": "Verified sources",
  "ledger.corrections": "Corrections", "ledger.retraction": "Retraction", "ledger.reports": "Reader reports",
  "ledger.bestOf": " · best {counted} of {cited}", "ledger.sourcesN": " · {n} sources", "ledger.source1": " · 1 source",
  "article.approvedBy": "Approved by", "article.sources": "Sources",
  "article.sourcesNote": "The five best sources add to the score, by what kind of source each is.",
  "article.howGraded": "How sources are graded", "article.continueReading": "Continue reading",
  "article.forSubscribers": "This article is published for {name}’s subscribers.",
  "article.subscribeToRead": "Subscribe to read", "article.createAccount": "Create an account",
  "article.haveAccount": "Already have one? Sign in", "article.whatCosts": "What a subscription costs",
  "article.share": "Share", "article.hideShare": "Hide sharing", "article.history": "Revision history",
  "article.hideHistory": "Hide history", "article.downloadPdf": "Download PDF",
  "article.downloadSlides": "Download slides", "article.scoreLabel": "Credibility score",
  "listen.group": "Listen to this article", "listen.listen": "Listen", "listen.pause": "Pause",
  "listen.resume": "Resume", "listen.keyPoints": "Key points", "listen.fullArticle": "Full article",
  "listen.min": "{n} min", "listen.stop": "Stop listening", "listen.speed": "Reading speed",
  "listen.modes": "What to listen to", "listen.posBrief": "Position in the key points",
  "listen.posArticle": "Position in the article", "listen.inBrief": "In brief.",
  "brief.title": "In brief", "brief.minRead": "{n} min read", "brief.method": "AI generated",
  "analysis.title": "Tone and trend", "analysis.tone": "Tone of the writing",
  "analysis.scale": "{score} on a scale from −1 (negative) to +1 (positive)",
  "analysis.share": "{p}% of sentences positive, {n}% negative",
  "analysis.paragraphs": "Tone of each paragraph, in reading order",
  "analysis.paragraph": "Paragraph {i}: {v}",
  "analysis.paragraphCaption": "Each bar is a paragraph, in order: above the line reads positive, below it negative.",
  "analysis.mostPositive": "Most positive line", "analysis.mostNegative": "Most negative line",
  "analysis.topicTone": "Other {topic} articles from the last eight weeks: {label} ({score}).",
  "analysis.interest": "Reader interest",
  "analysis.views": "{n} views in the last 14 days · {total} in total",
  "analysis.engagement": " · {likes} likes and {comments} comments in that time",
  "analysis.viewsChart": "Views per day over the last 14 days", "analysis.viewsDay": "{day}: {n} views",
  "analysis.viewsCaption": "Views per day, {from} to {to}. Rising or falling compares the last seven days with the seven before.",
  "analysis.coverage": "Coverage of", "analysis.weekChart": "{topic} articles published per week, last eight weeks",
  "analysis.week": "Week to {day}: {n} articles",
  "analysis.coverageCaption": "Articles published per week in this section, about {avg} a week on average.",
  "analysis.note": "Tone describes the wording, not whether the article is accurate: careful reporting of bad news reads negative. Scored automatically with VADER, a standard sentiment model.",
  "direction.rising": "Rising", "direction.steady": "Steady", "direction.falling": "Falling",
  "direction.quiet": "No recent views",
  "tone.positive": "Positive", "tone.leans_positive": "Leans positive", "tone.neutral": "Neutral",
  "tone.leans_negative": "Leans negative", "tone.negative": "Negative",
  "similar.title": "More like this",
  "writer.about": "About the writer", "writer.followers": "{n} followers", "writer.follower1": "1 follower",
  "writer.subscribe": "Subscribe", "writer.subscribed": "Subscribed", "writer.follow": "Follow",
  "writer.following": "Following", "writer.signIn": "Sign in",
  "writer.signInNote": "or create a free account to follow or subscribe.",
  "topics.title": "All topics",
  "topics.lead": "Every section of Sterling Wire. Each article is scored by the same rules, whichever section it is in.",
  "topics.articles": "{n} articles", "topics.byCountry": "Looking for a place instead?",
  "topics.browseCountry": "Browse by country", "countries.title": "Countries",
  "countries.lead": "News by the country it is about. Only countries with published articles are listed.",
  "list.articles": "Articles", "list.published": "{n} published", "list.loading": "Loading",
  "list.mostRecent": "Most recent", "list.highest": "Highest credibility", "list.allSections": "All sections",
  "translation.showing": "Showing English",
};

const zh = {
  "lang.label": "语言",
  "search.label": "按标题、标签或栏目搜索文章", "search.placeholder": "标题、标签或栏目",
  "search.how": "仅按关键词匹配，没有语义搜索，也没有个性化排序。结果按可信度排序，其次按发布时间。搜索使用文章的英文原文。",
  "search.none": "没有找到结果", "search.noneText": "没有与“{q}”匹配的内容。请尝试更宽泛的词语或栏目名称。",
  "search.count": "{n} 条结果", "search.countOne": "1 条结果",
  "search.prompt": "您想找什么？", "search.promptText": "搜索会匹配文章标题、标签和栏目名称。",
  "nav.browse": "浏览", "nav.search": "搜索", "nav.pricing": "订阅价格", "nav.signIn": "登录",
  "nav.createAccount": "注册账户", "nav.yourWriting": "我的文章", "nav.reviewQueue": "审稿队列",
  "nav.flagged": "被举报内容", "nav.admin": "管理",
  "browse.title": "浏览", "browse.topics": "主题", "browse.countries": "国家和地区",
  "browse.allTopics": "全部主题", "browse.allCountries": "全部国家和地区", "browse.home": "首页",
  "browse.aboutUs": "关于我们", "browse.howScoring": "评分说明", "browse.digests": "月度精选",
  "browse.editors": "编辑团队", "browse.pricing": "订阅价格", "browse.featured": "推荐",
  "browse.featuredTitle": "本月最可信的报道", "browse.featuredNote": "各栏目核实最充分的文章，以及我们发布的更正。",
  "browse.close": "关闭菜单",
  "account.menu": "账户菜单", "account.yourAccount": "我的账户", "account.readingList": "稍后阅读",
  "account.liked": "已点赞的文章", "account.subscriptions": "我的订阅", "account.signOut": "退出登录",
  "footer.tagline": "Sterling Wire。每篇文章都按同一套固定规则评分。",
  "footer.aboutUs": "关于我们", "footer.howScoring": "评分说明", "footer.allTopics": "全部主题",
  "footer.digests": "月度精选", "footer.countries": "国家和地区", "footer.editors": "编辑团队",
  "footer.subscriptions": "订阅", "footer.search": "搜索", "footer.privacy": "隐私", "footer.terms": "使用条款",
  "home.credibility": "可信度", "home.trace": "查看评分依据", "home.alsoToday": "今日其他报道",
  "home.articles": "{n} 篇文章", "home.inYourCategories": "您关注的栏目", "home.fromFollowed": "您关注的作者",
  "home.nothing": "暂无已发表的文章", "home.nothingNote": "编辑批准第一篇文章后，它会立即显示在这里。",
  "home.nothingCats": "您关注的栏目暂无文章", "home.nothingCatsNote": "多选几个感兴趣的栏目，这里就会丰富起来。",
  "band.High": "高", "band.Moderate": "中", "band.Low": "低", "band.Disputed": "存疑",
  "cred.accuracy": "准确率 {rate}%", "cred.new": "新作者", "cred.score": "可信度评分",
  "cred.notReviewed": "尚未审核", "cred.notReviewedLong": "尚未经编辑审核",
  "cred.arithmetic": "这是计算，而非预测。", "cred.howCalculated": "评分如何计算",
  "ledger.accuracy": "作者准确率", "ledger.sources": "已核实的来源", "ledger.corrections": "更正",
  "ledger.retraction": "撤稿", "ledger.reports": "读者举报",
  "ledger.bestOf": " · {cited} 个中最好的 {counted} 个", "ledger.sourcesN": " · {n} 个来源", "ledger.source1": " · 1 个来源",
  "article.approvedBy": "审核编辑", "article.sources": "资料来源",
  "article.sourcesNote": "最好的五个来源计入评分，按来源类型加分。", "article.howGraded": "来源如何评级",
  "article.continueReading": "继续阅读", "article.forSubscribers": "本文仅供 {name} 的订阅者阅读。",
  "article.subscribeToRead": "订阅后阅读", "article.createAccount": "注册账户",
  "article.haveAccount": "已有账户？登录", "article.whatCosts": "订阅费用",
  "article.share": "分享", "article.hideShare": "收起分享", "article.history": "修订记录",
  "article.hideHistory": "收起记录", "article.downloadPdf": "下载 PDF", "article.downloadSlides": "下载幻灯片",
  "article.scoreLabel": "可信度评分",
  "listen.group": "收听本文", "listen.listen": "收听", "listen.pause": "暂停", "listen.resume": "继续",
  "listen.keyPoints": "要点", "listen.fullArticle": "全文", "listen.min": "{n} 分钟", "listen.stop": "停止收听",
  "listen.speed": "朗读速度", "listen.modes": "收听内容", "listen.posBrief": "要点中的位置",
  "listen.posArticle": "文章中的位置", "listen.inBrief": "要点。",
  "brief.title": "要点", "brief.minRead": "阅读约 {n} 分钟", "brief.method": "人工智能生成",
  "analysis.title": "语气与趋势", "analysis.tone": "行文语气",
  "analysis.scale": "{score}（范围从 −1 负面到 +1 正面）", "analysis.share": "{p}% 的句子偏正面，{n}% 偏负面",
  "analysis.paragraphs": "各段语气（按阅读顺序）", "analysis.paragraph": "第 {i} 段：{v}",
  "analysis.paragraphCaption": "每根柱代表一段，按顺序排列：线上偏正面，线下偏负面。",
  "analysis.mostPositive": "最正面的句子", "analysis.mostNegative": "最负面的句子",
  "analysis.topicTone": "过去八周{topic}栏目的其他文章：{label}（{score}）。",
  "analysis.interest": "读者关注度", "analysis.views": "过去 14 天 {n} 次阅读 · 累计 {total} 次",
  "analysis.engagement": " · 同期 {likes} 个赞和 {comments} 条评论",
  "analysis.viewsChart": "过去 14 天的每日阅读量", "analysis.viewsDay": "{day}：{n} 次阅读",
  "analysis.viewsCaption": "每日阅读量，{from} 至 {to}。上升或下降是比较最近七天与此前七天。",
  "analysis.coverage": "栏目报道量：", "analysis.weekChart": "过去八周{topic}栏目每周发表的文章数",
  "analysis.week": "截至 {day} 的一周：{n} 篇",
  "analysis.coverageCaption": "本栏目每周发表的文章数，平均每周约 {avg} 篇。",
  "analysis.note": "语气描述的是措辞，而不是文章是否准确：认真报道坏消息也会显得负面。由标准情感分析模型 VADER 自动评分。",
  "direction.rising": "上升", "direction.steady": "平稳", "direction.falling": "下降", "direction.quiet": "近期无人阅读",
  "tone.positive": "正面", "tone.leans_positive": "偏正面", "tone.neutral": "中性",
  "tone.leans_negative": "偏负面", "tone.negative": "负面",
  "similar.title": "相关文章",
  "writer.about": "关于作者", "writer.followers": "{n} 位关注者", "writer.follower1": "1 位关注者",
  "writer.subscribe": "订阅", "writer.subscribed": "已订阅", "writer.follow": "关注", "writer.following": "已关注",
  "writer.signIn": "登录", "writer.signInNote": "或注册免费账户，即可关注或订阅。",
  "topics.title": "全部主题", "topics.lead": "Sterling Wire 的所有栏目。无论哪个栏目，每篇文章都按同一套规则评分。",
  "topics.articles": "{n} 篇文章", "topics.byCountry": "想按地区查找？", "topics.browseCountry": "按国家和地区浏览",
  "countries.title": "国家和地区", "countries.lead": "按报道所涉国家和地区浏览新闻。仅列出已有发表文章的国家和地区。",
  "list.articles": "文章", "list.published": "已发表 {n} 篇", "list.loading": "加载中",
  "list.mostRecent": "最新", "list.highest": "可信度最高", "list.allSections": "全部栏目",
  "translation.showing": "显示英文原文",
};

const ms = {
  "lang.label": "Bahasa",
  "search.label": "Cari artikel mengikut tajuk, tag atau kategori", "search.placeholder": "Tajuk, tag atau kategori",
  "search.how": "Padanan kata kunci sahaja. Tiada carian semantik dan tiada susunan peribadi. Hasil disusun mengikut kredibiliti, kemudian yang terkini. Carian menggunakan teks asal bahasa Inggeris.",
  "search.none": "Tiada hasil ditemui", "search.noneText": "Tiada yang sepadan dengan “{q}”. Cuba perkataan yang lebih umum, atau nama kategori.",
  "search.count": "{n} hasil", "search.countOne": "1 hasil",
  "search.prompt": "Apa yang anda cari?", "search.promptText": "Carian memadankan tajuk artikel, tag dan nama kategori.",
  "nav.browse": "Layari", "nav.search": "Cari", "nav.pricing": "Harga", "nav.signIn": "Log masuk",
  "nav.createAccount": "Daftar akaun", "nav.yourWriting": "Tulisan anda", "nav.reviewQueue": "Barisan semakan",
  "nav.flagged": "Dilaporkan", "nav.admin": "Pentadbiran",
  "browse.title": "Layari", "browse.topics": "Topik", "browse.countries": "Negara",
  "browse.allTopics": "Semua topik", "browse.allCountries": "Semua negara", "browse.home": "Laman utama",
  "browse.aboutUs": "Tentang kami", "browse.howScoring": "Cara pemarkahan", "browse.digests": "Ringkasan bulanan",
  "browse.editors": "Editor kami", "browse.pricing": "Harga", "browse.featured": "Pilihan",
  "browse.featuredTitle": "Laporan paling boleh dipercayai bulan ini",
  "browse.featuredNote": "Artikel paling teliti disahkan dari setiap seksyen, dan pembetulan yang kami buat.",
  "browse.close": "Tutup menu",
  "account.menu": "Menu akaun anda", "account.yourAccount": "Akaun anda", "account.readingList": "Senarai bacaan",
  "account.liked": "Artikel yang disukai", "account.subscriptions": "Langganan", "account.signOut": "Log keluar",
  "footer.tagline": "Sterling Wire. Setiap artikel dinilai dengan peraturan tetap yang sama.",
  "footer.aboutUs": "Tentang kami", "footer.howScoring": "Cara pemarkahan", "footer.allTopics": "Semua topik",
  "footer.digests": "Ringkasan bulanan", "footer.countries": "Negara", "footer.editors": "Editor kami",
  "footer.subscriptions": "Langganan", "footer.search": "Cari", "footer.privacy": "Privasi", "footer.terms": "Terma",
  "home.credibility": "Kredibiliti", "home.trace": "Lihat asas skor ini", "home.alsoToday": "Juga hari ini",
  "home.articles": "{n} artikel", "home.inYourCategories": "Dalam kategori anda",
  "home.fromFollowed": "Daripada penulis yang anda ikuti", "home.nothing": "Belum ada artikel diterbitkan",
  "home.nothingNote": "Artikel pertama akan muncul di sini sebaik sahaja editor meluluskannya.",
  "home.nothingCats": "Belum ada artikel dalam kategori anda",
  "home.nothingCatsNote": "Pilih beberapa minat lagi dan halaman ini akan terisi.",
  "band.High": "Tinggi", "band.Moderate": "Sederhana", "band.Low": "Rendah", "band.Disputed": "Dipertikai",
  "cred.accuracy": "Ketepatan {rate}%", "cred.new": "Penulis baharu", "cred.score": "Skor kredibiliti",
  "cred.notReviewed": "Belum disemak", "cred.notReviewedLong": "Belum disemak oleh editor",
  "cred.arithmetic": "Kiraan, bukan ramalan.", "cred.howCalculated": "Cara skor ini dikira",
  "ledger.accuracy": "Ketepatan penulis", "ledger.sources": "Sumber yang disahkan", "ledger.corrections": "Pembetulan",
  "ledger.retraction": "Penarikan balik", "ledger.reports": "Laporan pembaca",
  "ledger.bestOf": " · {counted} terbaik daripada {cited}", "ledger.sourcesN": " · {n} sumber", "ledger.source1": " · 1 sumber",
  "article.approvedBy": "Diluluskan oleh", "article.sources": "Sumber",
  "article.sourcesNote": "Lima sumber terbaik menambah skor, mengikut jenis setiap sumber.",
  "article.howGraded": "Cara sumber dinilai", "article.continueReading": "Teruskan membaca",
  "article.forSubscribers": "Artikel ini diterbitkan untuk pelanggan {name}.",
  "article.subscribeToRead": "Langgan untuk membaca", "article.createAccount": "Daftar akaun",
  "article.haveAccount": "Sudah ada akaun? Log masuk", "article.whatCosts": "Kos langganan",
  "article.share": "Kongsi", "article.hideShare": "Sembunyikan perkongsian", "article.history": "Sejarah semakan",
  "article.hideHistory": "Sembunyikan sejarah", "article.downloadPdf": "Muat turun PDF",
  "article.downloadSlides": "Muat turun slaid", "article.scoreLabel": "Skor kredibiliti",
  "listen.group": "Dengar artikel ini", "listen.listen": "Dengar", "listen.pause": "Jeda", "listen.resume": "Sambung",
  "listen.keyPoints": "Perkara utama", "listen.fullArticle": "Artikel penuh", "listen.min": "{n} min",
  "listen.stop": "Berhenti mendengar", "listen.speed": "Kelajuan bacaan", "listen.modes": "Apa yang hendak didengar",
  "listen.posBrief": "Kedudukan dalam perkara utama", "listen.posArticle": "Kedudukan dalam artikel",
  "listen.inBrief": "Ringkasan.",
  "brief.title": "Ringkasan", "brief.minRead": "Bacaan {n} min", "brief.method": "Dijana oleh AI",
  "analysis.title": "Nada dan trend", "analysis.tone": "Nada penulisan",
  "analysis.scale": "{score} pada skala −1 (negatif) hingga +1 (positif)",
  "analysis.share": "{p}% ayat positif, {n}% negatif",
  "analysis.paragraphs": "Nada setiap perenggan, mengikut susunan bacaan", "analysis.paragraph": "Perenggan {i}: {v}",
  "analysis.paragraphCaption": "Setiap bar ialah satu perenggan, mengikut susunan: di atas garisan positif, di bawahnya negatif.",
  "analysis.mostPositive": "Ayat paling positif", "analysis.mostNegative": "Ayat paling negatif",
  "analysis.topicTone": "Artikel {topic} lain dalam lapan minggu lalu: {label} ({score}).",
  "analysis.interest": "Minat pembaca", "analysis.views": "{n} tontonan dalam 14 hari lalu · {total} kesemuanya",
  "analysis.engagement": " · {likes} suka dan {comments} komen dalam tempoh itu",
  "analysis.viewsChart": "Tontonan sehari dalam 14 hari lalu", "analysis.viewsDay": "{day}: {n} tontonan",
  "analysis.viewsCaption": "Tontonan sehari, {from} hingga {to}. Naik atau turun membandingkan tujuh hari terakhir dengan tujuh hari sebelumnya.",
  "analysis.coverage": "Liputan", "analysis.weekChart": "Artikel {topic} diterbitkan setiap minggu, lapan minggu lalu",
  "analysis.week": "Minggu hingga {day}: {n} artikel",
  "analysis.coverageCaption": "Artikel diterbitkan setiap minggu dalam seksyen ini, purata kira-kira {avg} seminggu.",
  "analysis.note": "Nada menggambarkan pilihan kata, bukan ketepatan artikel: laporan teliti tentang berita buruk akan kedengaran negatif. Dinilai secara automatik dengan VADER, model sentimen yang standard.",
  "direction.rising": "Meningkat", "direction.steady": "Stabil", "direction.falling": "Menurun",
  "direction.quiet": "Tiada tontonan terkini",
  "tone.positive": "Positif", "tone.leans_positive": "Cenderung positif", "tone.neutral": "Neutral",
  "tone.leans_negative": "Cenderung negatif", "tone.negative": "Negatif",
  "similar.title": "Artikel berkaitan",
  "writer.about": "Tentang penulis", "writer.followers": "{n} pengikut", "writer.follower1": "1 pengikut",
  "writer.subscribe": "Langgan", "writer.subscribed": "Dilanggan", "writer.follow": "Ikuti", "writer.following": "Mengikuti",
  "writer.signIn": "Log masuk", "writer.signInNote": "atau daftar akaun percuma untuk mengikuti atau melanggan.",
  "topics.title": "Semua topik",
  "topics.lead": "Setiap seksyen Sterling Wire. Setiap artikel dinilai dengan peraturan yang sama, tanpa mengira seksyennya.",
  "topics.articles": "{n} artikel", "topics.byCountry": "Mencari mengikut tempat?", "topics.browseCountry": "Layari mengikut negara",
  "countries.title": "Negara",
  "countries.lead": "Berita mengikut negara yang dilaporkan. Hanya negara yang mempunyai artikel diterbitkan disenaraikan.",
  "list.articles": "Artikel", "list.published": "{n} diterbitkan", "list.loading": "Memuatkan",
  "list.mostRecent": "Terkini", "list.highest": "Kredibiliti tertinggi", "list.allSections": "Semua seksyen",
  "translation.showing": "Memaparkan bahasa Inggeris",
};

const DICTS = { en, zh, ms };

/** Section and country names, which come from the server in English. */
const SECTIONS = {
  zh: { politics: "政治", technology: "科技", business: "商业", health: "健康", science: "科学",
        environment: "环境", sport: "体育", uncategorised: "未分类" },
  ms: { politics: "Politik", technology: "Teknologi", business: "Perniagaan", health: "Kesihatan",
        science: "Sains", environment: "Alam sekitar", sport: "Sukan", uncategorised: "Tidak berkategori" },
};
const COUNTRIES = {
  zh: { AU: "澳大利亚", NZ: "新西兰", SG: "新加坡", JP: "日本", GB: "英国", US: "美国", MY: "马来西亚",
        CN: "中国", IN: "印度" },
  ms: { AU: "Australia", NZ: "New Zealand", SG: "Singapura", JP: "Jepun", GB: "United Kingdom",
        US: "Amerika Syarikat", MY: "Malaysia", CN: "China", IN: "India" },
};

let current = "en";

/** The language now in use, for code outside React (dates, the API client). */
export function currentLang() {
  return current;
}

export function translate(lang, key, vars) {
  const text = DICTS[lang]?.[key] ?? en[key] ?? key;
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (_, name) => (vars[name] ?? `{${name}}`));
}

function readStored() {
  try {
    const value = window.localStorage.getItem(STORE);
    return DICTS[value] ? value : "en";
  } catch {
    return "en";
  }
}

const I18nContext = createContext({ lang: "en", setLang: () => {}, t: (k, v) => translate("en", k, v) });

export function LanguageProvider({ children }) {
  const [lang, setLangState] = useState(readStored);
  current = lang;
  setApiLang(lang);

  useEffect(() => {
    const meta = LANGUAGES.find((l) => l.code === lang);
    document.documentElement.lang = meta?.html || "en";
  }, [lang]);

  const value = useMemo(() => ({
    lang,
    setLang(next) {
      if (!DICTS[next]) return;
      try {
        window.localStorage.setItem(STORE, next);
      } catch {
        /* storage blocked: the choice lasts for this visit only */
      }
      current = next;
      setApiLang(next);
      setLangState(next);
    },
    t: (key, vars) => translate(lang, key, vars),
    section: (slug, name) => SECTIONS[lang]?.[slug] ?? name,
    country: (code, name) => COUNTRIES[lang]?.[code] ?? name,
  }), [lang]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  return useContext(I18nContext);
}
